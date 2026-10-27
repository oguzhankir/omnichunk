"""Replay predeclared context budgets from exact frozen vectors, ranking once.

This utility performs no model inference and never reads corpus documents. It
requires a successful 512-token dense report, verifies its original rankings,
selection and scores exactly, then reuses each ranking for every requested budget.
Original timing fields are retained as provenance, not measured frontier latency.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(
    os.environ.get("OMNICHUNK_FROZEN_HARNESS", "/workspace/work/omnichunk-v3/frozen-candidate-v2")
)
sys.path.insert(0, str(HARNESS_ROOT))
sys.path.insert(0, str(HARNESS_ROOT / "src"))

from benchmarks.retrieval.adapters import Passage  # noqa: E402
from benchmarks.retrieval.dense import FrozenDenseRetriever  # noqa: E402
from benchmarks.retrieval.ranking import select_budget  # noqa: E402
from benchmarks.retrieval.tokenization import benchmark_counter  # noqa: E402
from benchmarks.run_retrieval import _summarize  # noqa: E402
from omnichunk.retrieval_eval import EvidenceSpan, score_evidence, score_ranking  # noqa: E402

DEFAULT_BUDGETS = (128, 256, 512)
ANCHOR_BUDGET = 512
SHARED_TIMING_SCOPE = (
    "Original chunk/index/query/encoder timing fields are retained unchanged from "
    "the input 512-token report. One additional frozen ranking per candidate/query "
    "is shared across all frontier budgets solely to verify/replay results. No "
    "per-budget ranking, encoding or end-to-end latency was measured."
)


def _hash_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _json_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def _require_equal(actual: Any, expected: Any, description: str) -> None:
    if actual != expected:
        raise ValueError(f"Original 512-token report mismatch: {description}")


def _validate_budgets(budgets: Sequence[int]) -> tuple[int, ...]:
    if not budgets or any(type(value) is not int or value < 1 for value in budgets):
        raise ValueError("Frontier budgets must be positive integers")
    if len(set(budgets)) != len(budgets):
        raise ValueError("Frontier budgets must be distinct")
    return tuple(budgets)


@contextmanager
def _decoded_vectors(path: Path) -> Iterator[Path]:
    if path.suffix != ".gz":
        yield path
        return
    scratch = Path(__file__).resolve().parent / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="frontier-vectors-", dir=scratch) as temporary:
        decoded = Path(temporary) / "vectors.json"
        with gzip.open(path, "rb") as source, decoded.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        yield decoded


def _verify_harness(report: dict[str, Any]) -> dict[str, str]:
    paths = (
        "benchmarks/retrieval/dense.py",
        "benchmarks/retrieval/ranking.py",
        "benchmarks/retrieval/tokenization.py",
        "benchmarks/run_retrieval.py",
    )
    original = report["environment"]["harness_files"]
    observed = {name: _hash_file(HARNESS_ROOT / name) for name in paths}
    for name, digest in observed.items():
        _require_equal(digest, original.get(name), f"shared harness file {name}")
    return observed


def _verify_tokenizer(directory: Path, embedding_metadata: dict[str, Any]) -> dict[str, str]:
    """Bind native token counting to the originally recorded local asset bytes."""
    recorded = embedding_metadata["producer_metadata"]["model_files"]
    suffixes = {".json", ".txt", ".model"}
    selected = {name: digest for name, digest in recorded.items() if Path(name).suffix in suffixes}
    if "tokenizer_config.json" not in selected:
        raise ValueError("Original producer metadata lacks native tokenizer assets")
    observed = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            name = path.relative_to(directory).as_posix()
            if name not in selected:
                raise ValueError(f"Local tokenizer directory has an unrecorded asset: {name}")
            observed[name] = _hash_file(path)
    _require_equal(observed, selected, "native tokenizer/config asset SHA-256 values")
    return observed


def _spans(ranked: Sequence[tuple[Passage, float]]) -> list[EvidenceSpan]:
    return [EvidenceSpan(p.source_id, p.start, p.end) for p, _ in ranked]


def _derive_candidate(
    original: dict[str, Any],
    retriever: FrozenDenseRetriever,
    counter: Callable[[str], int],
    budgets: Sequence[int],
    *,
    top_k: int,
) -> tuple[dict[int, dict[str, Any]], int]:
    """Validate one original candidate and rank each query exactly once."""
    if original.get("status") != "ok":
        raise ValueError("Every frontier input candidate must have status='ok'")
    passages = [Passage(**item) for item in original["passages"]]
    _require_equal(len(passages), original["chunks"], "passage count")
    for passage in passages:
        if passage.start < 0 or passage.end <= passage.start:
            raise ValueError("Report passages must have positive source ranges")
        if passage.end - passage.start != len(passage.text.encode("utf-8")):
            raise ValueError("Report passage range differs from its UTF-8 byte length")
    _require_equal(_summarize(original["per_query"]), original["summary"], "input summary")
    query_ids = [query["query_id"] for query in original["per_query"]]
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("Original report has duplicate query IDs")
    derived = {budget: deepcopy(original) for budget in budgets}
    for candidate in derived.values():
        candidate["per_query"] = []
    index = retriever.index(passages)
    calls = 0
    for query in original["per_query"]:
        ranked = index.rank(query["query"])
        calls += 1
        query_id = query["query_id"]
        rows = [
            {
                "passage_id": passage.passage_id,
                "source_id": passage.source_id,
                "start": passage.start,
                "end": passage.end,
                "score": score,
            }
            for passage, score in ranked[:top_k]
        ]
        _require_equal(rows, query["ranks"], f"{query_id}: top-k IDs, ranges and cosine scores")
        gold = [EvidenceSpan(**span) for span in query["evidence"]]
        qrels = {
            passage.passage_id: 1.0
            for passage in passages
            if any(
                passage.source_id == evidence.source_id
                and max(passage.start, evidence.start) < min(passage.end, evidence.end)
                for evidence in gold
            )
        }
        ranking = asdict(score_ranking([p.passage_id for p, _ in ranked], qrels, k=top_k))
        _require_equal(ranking, query["ranking"], f"{query_id}: ranking metrics")
        _require_equal(len(qrels), query["relevant_passages"], f"{query_id}: relevant passages")
        _require_equal(
            asdict(score_evidence(_spans(ranked[:top_k]), gold)),
            query["evidence_at_k"],
            f"{query_id}: top-k source-evidence metrics",
        )
        # Always validate the original anchor, even if 512 is not an output budget.
        selections = {}
        for budget in dict.fromkeys((ANCHOR_BUDGET, *budgets)):
            selected = select_budget(ranked, budget, counter)
            used = counter("\n\n".join(p.text for p, _ in selected)) if selected else 0
            evidence = asdict(score_evidence(_spans(selected), gold))
            ids = [passage.passage_id for passage, _ in selected]
            if used > budget:
                raise ValueError("Frontier context overflowed its complete-input budget")
            selections[budget] = (ids, used, evidence)
        ids, used, evidence = selections[ANCHOR_BUDGET]
        _require_equal(ids, query["budget_passage_ids"], f"{query_id}: 512 prefix IDs/order")
        _require_equal(used, query["budget_used"], f"{query_id}: 512 native token count")
        _require_equal(evidence, query["evidence_at_budget"], f"{query_id}: 512 evidence metrics")
        for budget, candidate in derived.items():
            ids, used, evidence = selections[budget]
            updated = deepcopy(query)
            updated["budget_passage_ids"] = ids
            updated["budget_used"] = used
            updated["evidence_at_budget"] = evidence
            candidate["per_query"].append(updated)
    for budget, candidate in derived.items():
        candidate["summary"] = _summarize(candidate["per_query"])
        if budget == ANCHOR_BUDGET:
            _require_equal(candidate, original, "complete replayed 512 candidate")
    return derived, calls


def run(args: argparse.Namespace) -> dict[str, Any]:
    budgets = _validate_budgets(args.budgets)
    report_path, vectors_path = args.report.resolve(), args.vectors.resolve()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("--output-dir must be empty; preserve prior frontier evidence")
    raw_report = _json_bytes(report_path)
    original = json.loads(raw_report)
    config = original["configuration"]
    expected = {
        "retrieval_budget": ANCHOR_BUDGET,
        "retriever": "frozen-dense-cosine-v1",
        "unit": "tokens",
        "include_special_tokens": True,
        "budget_selection": "whole ranked prefix, including two newline separators",
    }
    for name, value in expected.items():
        _require_equal(config.get(name), value, f"configuration.{name}")
    if type(config["top_k"]) is not int or config["top_k"] < 1:
        raise ValueError("Original top-k must be a positive integer")
    if not original["candidates"]:
        raise ValueError("Original report contains no candidates")
    harness = _verify_harness(original)
    tokenizer = _verify_tokenizer(args.model_dir.resolve(), config["dense_embeddings"])
    counter = benchmark_counter(
        "tokens", str(args.model_dir.resolve()), include_special_tokens=True
    )
    reports = {budget: deepcopy(original) for budget in budgets}
    for budget, report in reports.items():
        report["configuration"]["retrieval_budget"] = budget
        report["candidates"] = []
    calls = 0
    with _decoded_vectors(vectors_path) as decoded:
        retriever = FrozenDenseRetriever(
            decoded,
            corpus_manifest_sha256=original["corpus_manifest_sha256"],
            model_id=config["dense_embeddings"]["model_id"],
            model_revision=config["dense_embeddings"]["model_revision"],
            preprocessing_revision=config["dense_embeddings"]["preprocessing_revision"],
        )
        _require_equal(
            retriever.metadata, config["dense_embeddings"], "full frozen-vector metadata/hash"
        )
        for candidate in original["candidates"]:
            _require_equal(
                len(candidate["per_query"]), original["queries"], "candidate query count"
            )
            derived, count = _derive_candidate(
                candidate, retriever, counter, budgets, top_k=config["top_k"]
            )
            calls += count
            for budget in budgets:
                reports[budget]["candidates"].append(derived[budget])
        vectors_json_sha256 = _hash_file(decoded)
    metadata = {
        "schema_version": 1,
        "producer_source_sha256": _hash_file(Path(__file__).resolve()),
        "source_report_file_sha256": _hash_file(report_path),
        "source_report_json_sha256": hashlib.sha256(raw_report).hexdigest(),
        "source_vectors_file_sha256": _hash_file(vectors_path),
        "source_vectors_json_sha256": vectors_json_sha256,
        "shared_harness_files": harness,
        "verified_tokenizer_assets": tokenizer,
        "anchor_budget": ANCHOR_BUDGET,
        "requested_budgets": list(budgets),
        "anchor_replay_exact": True,
        "rank_calls_shared_across_budgets": calls,
        "embedding_calls": 0,
        "timing_scope": SHARED_TIMING_SCOPE,
        "interpretation": (
            "Predeclared secondary context-budget frontier; ranks and exact real vectors "
            "are shared. Original top-k metrics and provenance remain unchanged. "
            "Budgets are reported together, without selecting favorable outcomes."
        ),
    }
    # Validate every input and 512 anchor before creating any output artifact.
    serialized = {}
    for budget, report in reports.items():
        report["frontier"] = {**metadata, "derived_retrieval_budget": budget}
        serialized[budget] = (
            json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        )
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for budget, payload in serialized.items():
        path = output / f"budget-{budget}.report.json"
        path.write_text(payload, encoding="utf-8")
        entries.append(
            {
                "retrieval_budget": budget,
                "file": path.name,
                "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "candidates": [
                    {
                        "tool": candidate["tool"],
                        "chunk_capacity": candidate["chunk_capacity"],
                        "summary": candidate["summary"],
                    }
                    for candidate in reports[budget]["candidates"]
                ],
            }
        )
    summary = {**metadata, "outputs": entries}
    (output / "frontier.json").write_text(
        json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS))
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except (ValueError, OSError, ImportError, KeyError, TypeError) as exc:
        print(f"Frozen frontier replay failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "anchor_replay_exact": summary["anchor_replay_exact"],
                "budgets": summary["requested_budgets"],
                "shared_rank_calls": summary["rank_calls_shared_across_budgets"],
                "outputs": [
                    {"budget": item["retrieval_budget"], "file": item["file"]}
                    for item in summary["outputs"]
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
