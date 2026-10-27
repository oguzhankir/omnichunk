"""Run a declared dense comparison with an explicit local pretrained snapshot.

This command never downloads models. Preparation/evaluation use the same current
harness and frozen model for both source checkouts. Development is the default;
held-out results must be requested only after implementation/configuration freeze.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.retrieval.adapters import TOOLS as AVAILABLE_TOOLS  # noqa: E402

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TOOLS = ("omnichunk", "fixed", "semchunk", "langchain", "semantic-text-splitter", "llamaindex")


def _command(arguments: list[str], environment: dict[str, str], output: Path) -> None:
    with output.open("w", encoding="utf-8") as handle:
        subprocess.run(
            [sys.executable, *arguments],
            cwd=ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=True,
        )


def _compress(path: Path) -> Path:
    destination = path.with_suffix(path.suffix + ".gz")
    with (
        path.open("rb") as source,
        destination.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
    ):
        shutil.copyfileobj(source, compressed)
    path.unlink()
    return destination


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", args.model_revision):
        raise ValueError("--model-revision must be the frozen 40-character model commit")
    tools = getattr(args, "tools", ",".join(TOOLS)).split(",")
    if not tools or any(tool not in AVAILABLE_TOOLS for tool in tools):
        raise ValueError(f"--tools must be comma-separated names from {', '.join(AVAILABLE_TOOLS)}")
    if len(set(tools)) != len(tools):
        raise ValueError("--tools must not contain duplicate strategy names")
    anchor = "omnichunk" if "omnichunk" in tools else tools[0]
    snapshot = args.model_dir.resolve()
    if not snapshot.is_dir():
        raise ValueError("--model-dir must identify an existing local snapshot")
    baseline = args.baseline_dir.resolve()
    if not (baseline / "src/omnichunk/__init__.py").is_file():
        raise ValueError("--baseline-dir must contain a separate OmniChunk source checkout")
    candidate = Path(getattr(args, "candidate_dir", ROOT)).resolve()
    if not (candidate / "src/omnichunk/__init__.py").is_file():
        raise ValueError("--candidate-dir must contain an OmniChunk source checkout")
    corpus = (
        ROOT / "benchmarks/retrieval" / args.corpus
        if args.corpus in {"corpus_v1", "corpus_squad_v1"}
        else Path(args.corpus).expanduser().resolve()
    )
    if not (corpus.is_file() or (corpus / "manifest.json").is_file()):
        raise ValueError("--corpus must identify a corpus directory or manifest file")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("--output-dir must be empty; preserve prior experiment evidence")
    output.mkdir(parents=True, exist_ok=True)
    common = [
        "--corpus",
        str(corpus),
        "--split",
        args.split,
        "--tools",
        ",".join(tools),
        "--chunk-sizes",
        "64",
        "96",
        "--unit",
        "tokens",
        "--tokenizer",
        str(snapshot),
        "--include-special-tokens",
    ]
    environment = {
        **os.environ,
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONHASHSEED": "0",
    }
    reports = {}
    for label, checkout in (("baseline", baseline), ("candidate", candidate)):
        selected = {**environment, "PYTHONPATH": str(checkout / "src")}
        vectors = output / f"{label}.vectors.json"
        report = output / f"{label}.report.json"
        print(f"Preparing {label}: {args.corpus}/{args.split}", flush=True)
        _command(
            [
                "benchmarks/prepare_dense.py",
                *common,
                "--model-dir",
                str(snapshot),
                "--model-id",
                args.model_id,
                "--model-revision",
                args.model_revision,
                "--batch-size",
                "32",
                "--cpu-threads",
                "2",
                "--output",
                str(vectors),
            ],
            selected,
            output / f"{label}.preparation.json.log",
        )
        _command(
            [
                "benchmarks/run_retrieval.py",
                *common,
                "--retriever",
                "dense",
                "--dense-embeddings",
                str(vectors),
                "--retrieval-budget",
                "512",
                "--top-k",
                "5",
                "--repeats",
                "3",
                "--require-all",
                "--output",
                str(report),
            ],
            selected,
            output / f"{label}.evaluation.log",
        )
        reports[label] = report
        _compress(vectors)
    _command(
        [
            "benchmarks/compare_retrieval.py",
            "--baseline",
            str(reports["baseline"]),
            "--candidate",
            str(reports["candidate"]),
            "--baseline-tool",
            anchor,
            "--candidate-tool",
            anchor,
            "--output",
            str(output / "paired.json"),
        ],
        environment,
        output / "paired.log",
    )
    for rival in (tool for tool in tools if tool != anchor):
        _command(
            [
                "benchmarks/compare_retrieval.py",
                "--baseline",
                str(reports["candidate"]),
                "--baseline-tool",
                anchor,
                "--candidate",
                str(reports["candidate"]),
                "--candidate-tool",
                rival,
                "--output",
                str(output / f"{anchor}-vs-{rival}.json"),
            ],
            environment,
            output / f"{anchor}-vs-{rival}.log",
        )
    for report in reports.values():
        _compress(report)
    manifest = {
        "schema_version": 1,
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "corpus": args.corpus,
        "split": args.split,
        "tools": tools,
        "comparison_anchor_tool": anchor,
        "corpus_path": str(corpus),
        "chunk_token_capacities": [64, 96],
        "retrieved_context_tokens": 512,
        "top_k": 5,
        "repeats": 3,
        "cpu_threads": 2,
        "tokenizer": "snapshot native tokenizer, including special tokens",
        "include_special_tokens": True,
        "baseline_source": str(baseline),
        "candidate_source": str(candidate),
        "excluded": (
            {"chonkie": "count-only token callback cannot supply encode/decode semantics"}
            if "chonkie" not in tools
            else {}
        ),
        "interpretation": "Fixed experiment; no universal quality or end-to-end latency claim.",
    }
    (output / "experiment.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-id", default=MODEL)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, default=ROOT)
    parser.add_argument(
        "--corpus", required=True, help="Corpus path or historical bundled corpus name"
    )
    parser.add_argument("--tools", default=",".join(TOOLS))
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), allow_nan=False, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Dense experiment failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
