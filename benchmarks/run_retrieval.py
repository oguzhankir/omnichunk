"""Compare retrieval evidence at declared chunk and complete-context budgets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import tracemalloc
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import omnichunk  # noqa: E402
from benchmarks.retrieval.adapters import AdapterUnavailable, Passage, split_document  # noqa: E402
from benchmarks.retrieval.corpus import Corpus, load_corpus  # noqa: E402
from benchmarks.retrieval.ranking import (  # noqa: E402
    MODEL_REVISION,
    LexicalRetriever,
    select_budget,
)
from omnichunk import __version__  # noqa: E402
from omnichunk.retrieval_eval import EvidenceSpan, score_evidence, score_ranking  # noqa: E402
from omnichunk.sizing.counter import make_token_counter  # noqa: E402

DEFAULT_CORPUS = ROOT / "benchmarks" / "retrieval" / "corpus_v1"
TOOLS = (
    "omnichunk",
    "fixed",
    "semchunk",
    "langchain",
    "semantic-text-splitter",
    "chonkie",
    "llamaindex",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    dependencies = {}
    for name in (
        "omnichunk",
        "tree-sitter",
        "tree-sitter-python",
        "tiktoken",
        "semchunk",
        "langchain-text-splitters",
        "semantic-text-splitter",
        "chonkie",
        "llama-index-core",
    ):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    except ImportError:
        peak_bytes = None
    package_root = Path(omnichunk.__file__).resolve().parent
    source_files = sorted(package_root.rglob("*.py"))
    harness_files = [Path(__file__), *sorted((ROOT / "benchmarks" / "retrieval").glob("*.py"))]
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "omnichunk_version": __version__,
        "git_revision": revision,
        "dirty_checkout": dirty,
        "dependencies": dependencies,
        "runtime_package_root": str(package_root),
        "runtime_matches_checkout": package_root == (ROOT / "src" / "omnichunk").resolve(),
        "project_config_sha256": _sha256(ROOT / "pyproject.toml"),
        "source_sha256": hashlib.sha256(
            b"".join(
                p.relative_to(package_root).as_posix().encode() + p.read_bytes()
                for p in source_files
            )
        ).hexdigest(),
        "harness_files": {p.relative_to(ROOT).as_posix(): _sha256(p) for p in harness_files},
        "process_lifetime_peak_rss_bytes": peak_bytes,
        "memory_note": (
            "RSS is process lifetime, not per-candidate. Python peaks exclude native allocations."
        ),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups["all"] = rows
    for row in rows:
        groups[f"language:{row['language']}"].append(row)
        groups[f"category:{row['category']}"].append(row)
    output = {}
    for name, selected in sorted(groups.items()):
        output[name] = {"queries": len(selected)}
        for section, keys in (
            ("ranking", ("recall_at_k", "mrr_at_k", "ndcg_at_k")),
            ("evidence_at_k", ("precision", "recall", "iou")),
            ("evidence_at_budget", ("precision", "recall", "iou")),
        ):
            output[name][section] = {
                key: statistics.mean(row[section][key] for row in selected) for key in keys
            }
    return output


def _evaluate_candidate(
    corpus: Corpus,
    args: argparse.Namespace,
    tool: str,
    capacity: int,
    retriever: LexicalRetriever,
) -> dict[str, Any]:
    documents = [doc for doc in corpus.documents if doc.split == args.split]
    queries = [query for query in corpus.queries if query.split == args.split]
    counter = len if args.unit == "chars" else make_token_counter(args.tokenizer)

    def chunk_all() -> list[Passage]:
        return [
            passage
            for doc in documents
            for passage in split_document(
                tool, doc.source_id, doc.path, doc.text, capacity, counter, args.unit
            )
        ]

    candidate: dict[str, Any] = {"tool": tool, "chunk_capacity": capacity}
    try:
        passages = chunk_all()  # Untimed import/parser warmup and reference output.
        samples = []
        for _ in range(args.repeats):
            started = perf_counter()
            repeated = chunk_all()
            samples.append(perf_counter() - started)
            if repeated != passages:
                raise ValueError("Adapter output changed between repeated runs")
        tracemalloc.start()
        try:
            measured_passages = chunk_all()
            if measured_passages != passages:
                raise ValueError("Adapter output changed during memory measurement")
            _, chunk_peak = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            started = perf_counter()
            index = retriever.index(measured_passages)
            index_seconds = perf_counter() - started
            _, index_peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        ids = [passage.passage_id for passage in passages]
        if len(set(ids)) != len(ids):
            raise ValueError("Adapter produced duplicate passage IDs")
        by_source = {doc.source_id: doc for doc in documents}
        rows = []
        query_samples = []
        for query in queries:
            started = perf_counter()
            ranked = index.rank(query.text)
            query_samples.append(perf_counter() - started)
            qrels = {
                passage.passage_id: 1.0
                for passage in passages
                if any(
                    passage.source_id == evidence.source_id
                    and max(passage.start, evidence.start) < min(passage.end, evidence.end)
                    for evidence in query.evidence
                )
            }
            budgeted = select_budget(ranked, args.retrieval_budget, counter)

            def spans(items: list[tuple[Passage, float]]) -> list[EvidenceSpan]:
                return [EvidenceSpan(p.source_id, p.start, p.end) for p, _ in items]

            doc = by_source[query.evidence[0].source_id]
            rows.append(
                {
                    "query_id": query.query_id,
                    "query": query.text,
                    "language": doc.language,
                    "category": doc.category,
                    "ranking": asdict(
                        score_ranking([p.passage_id for p, _ in ranked], qrels, k=args.top_k)
                    ),
                    "evidence_at_k": asdict(
                        score_evidence(spans(ranked[: args.top_k]), query.evidence)
                    ),
                    "evidence_at_budget": asdict(score_evidence(spans(budgeted), query.evidence)),
                    "budget_used": counter("\n\n".join(p.text for p, _ in budgeted)),
                    "relevant_passages": len(qrels),
                    "ranks": [
                        {
                            "passage_id": p.passage_id,
                            "source_id": p.source_id,
                            "start": p.start,
                            "end": p.end,
                            "score": score,
                        }
                        for p, score in ranked[: args.top_k]
                    ],
                    "budget_passage_ids": [p.passage_id for p, _ in budgeted],
                    "evidence": [asdict(evidence) for evidence in query.evidence],
                }
            )
        candidate.update(
            {
                "status": "ok",
                "summary": _summarize(rows),
                "per_query": rows,
                "chunks": len(passages),
                "payload_utf8_bytes": sum(len(p.text.encode()) for p in passages),
                "max_payload_size": max((counter(p.text) for p in passages), default=0),
                "chunk_seconds_samples": samples,
                "chunk_seconds_median": statistics.median(samples),
                "index_seconds": index_seconds,
                "query_seconds_samples": query_samples,
                "python_chunk_peak_bytes": chunk_peak,
                "python_index_peak_bytes": index_peak,
                "embedding_calls": 0,
                "passages": [asdict(passage) for passage in passages],
            }
        )
    except AdapterUnavailable as exc:
        candidate.update(status="unavailable", detail=str(exc))
    except Exception as exc:
        candidate.update(status="error", detail=f"{type(exc).__name__}: {exc}")
    return candidate


def run(args: argparse.Namespace) -> dict[str, Any]:
    corpus = load_corpus(args.corpus)
    documents = [doc for doc in corpus.documents if doc.split == args.split]
    if not documents or not any(query.split == args.split for query in corpus.queries):
        raise ValueError(f"Corpus has no documents/queries for split {args.split!r}")
    started = perf_counter()
    retriever = LexicalRetriever([doc.text for doc in documents])
    fit_seconds = perf_counter() - started
    candidates = [
        _evaluate_candidate(corpus, args, tool, capacity, retriever)
        for tool in args.tools.split(",")
        for capacity in args.chunk_sizes
    ]
    return {
        "schema_version": 1,
        "corpus_id": corpus.corpus_id,
        "corpus_manifest_sha256": corpus.manifest_hash,
        "configuration": {
            "split": args.split,
            "tools": args.tools.split(","),
            "chunk_sizes": args.chunk_sizes,
            "unit": args.unit,
            "tokenizer": args.tokenizer if args.unit == "tokens" else "python-unicode-codepoints",
            "retrieval_budget": args.retrieval_budget,
            "top_k": args.top_k,
            "repeats": args.repeats,
            "context": "none",
            "overlap": 0,
            "retriever": MODEL_REVISION,
            "idf_fit": "selected source documents only; queries/labels excluded",
            "relevance": (
                "binary positive canonical-byte intersection; chunk-level qrels differ by candidate"
            ),
            "budget_selection": "whole ranked prefix, including two newline separators",
        },
        "interpretation": (
            "Synthetic lexical control; no dense model or external retrieval-quality claim. "
            "Compare source evidence at equal budgets."
        ),
        "documents": len(documents),
        "queries": sum(q.split == args.split for q in corpus.queries),
        "retriever_fit_seconds": fit_seconds,
        "environment": _environment(),
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--tools", default="omnichunk,fixed")
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[128, 256])
    parser.add_argument("--unit", choices=["chars", "tokens"], default="chars")
    parser.add_argument("--tokenizer", default="cl100k_base")
    parser.add_argument("--retrieval-budget", type=int, default=1024)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--require-all", action="store_true", help="Fail if any requested tool is unavailable"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if any(n < 1 for n in [*args.chunk_sizes, args.retrieval_budget, args.top_k, args.repeats]):
        parser.error("All capacities, top-k and repeat counts must be positive")
    if any(tool not in TOOLS for tool in args.tools.split(",")):
        parser.error(f"--tools must be comma-separated names from {', '.join(TOOLS)}")
    if args.unit == "tokens" and args.tokenizer == "approximate":
        parser.error("Retrieval comparisons require an exact tokenizer")
    try:
        report = run(args)
    except (ValueError, OSError, ImportError) as exc:
        print(f"Retrieval evaluation failed: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return int(
        any(
            candidate["status"] == "error" or (args.require_all and candidate["status"] != "ok")
            for candidate in report["candidates"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
