"""Compare paired source-evidence results from the same frozen experiment.

Intervals resample gold-source connected components, preserving within-document
query correlation. They assume those components are independent; they do not
establish a universal ranking or correct for selecting configurations/slices.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any

_CONFIG = (
    "split",
    "unit",
    "tokenizer",
    "retrieval_budget",
    "top_k",
    "context",
    "overlap",
    "retriever",
    "idf_fit",
    "relevance",
    "budget_selection",
)
_METRICS = ("precision", "recall", "iou")
_TOLERANCE = 1e-12


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate report JSON key: {key}")
        result[key] = value
    return result


def _validate_json(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_json(key)
            _validate_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Report JSON must contain finite numbers")
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("Report JSON must contain valid Unicode") from exc


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _positive(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _dense_contract(configuration: dict[str, Any]) -> dict[str, Any]:
    data = configuration.get("dense_embeddings")
    if not isinstance(data, dict):
        raise ValueError("Dense comparison requires embedding provenance")
    contract: dict[str, Any] = {}
    for key in ("model_id", "model_revision", "preprocessing_revision", "dimension"):
        if key not in data:
            raise ValueError(f"Dense comparison requires {key}")
        contract[key] = data[key]
    _positive(contract["dimension"], "Dense dimension")
    for key in ("model_id", "model_revision", "preprocessing_revision"):
        _name(contract[key], key)
    producer = data.get("producer_metadata")
    if not isinstance(producer, dict):
        raise ValueError("Dense comparison requires producer_metadata")
    for key in (
        "model_files",
        "packages",
        "prompt",
        "max_sequence_length",
        "supported_pipeline",
    ):
        if key not in producer:
            raise ValueError(f"Dense comparison requires producer_metadata.{key}")
        contract[key] = producer[key]
    if not isinstance(contract["model_files"], dict) or not contract["model_files"]:
        raise ValueError("Dense comparison requires nonempty model snapshot hashes")
    if not isinstance(contract["packages"], dict) or not contract["packages"]:
        raise ValueError("Dense comparison requires encoder package versions")
    _positive(contract["max_sequence_length"], "Model maximum sequence length")
    for revision in ("model_revision", "preprocessing_revision"):
        if contract[revision].casefold() in {"main", "master", "latest", "head"}:
            raise ValueError("Dense comparisons require frozen model/preprocessing revisions")
    for filename, digest in contract["model_files"].items():
        _name(filename, "Model snapshot filename")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("Model snapshot hashes must be lowercase SHA-256 digests")
    for package, version in contract["packages"].items():
        _name(package, "Encoder package name")
        _name(version, "Encoder package version")
    if not isinstance(contract["prompt"], str):
        raise ValueError("Encoder prompt must be a string")
    _name(contract["supported_pipeline"], "Supported encoder pipeline")
    for key in ("device", "input_policy", "normalization"):
        contract[key] = producer.get(key)
    return contract


def _selected(report: dict[str, Any], tool: str) -> dict[int, dict[str, Any]]:
    config = report.get("configuration")
    if not isinstance(config, dict) or not isinstance(config.get("chunk_sizes"), list):
        raise ValueError("Report requires configuration.chunk_sizes")
    capacities = config["chunk_sizes"]
    for capacity in capacities:
        _positive(capacity, "Chunk capacity")
    if not capacities or len(set(capacities)) != len(capacities):
        raise ValueError("Report capacities must be nonempty and unique")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
        raise ValueError("Report requires candidate objects")
    selected: dict[int, dict[str, Any]] = {}
    for candidate in candidates:
        if candidate.get("tool") != tool:
            continue
        capacity = _positive(candidate.get("chunk_capacity"), "Candidate chunk capacity")
        if capacity in selected:
            raise ValueError(f"Duplicate {tool} candidate at capacity {capacity}")
        if candidate.get("status") != "ok":
            raise ValueError(f"Selected {tool} candidate at capacity {capacity} is not successful")
        selected[capacity] = candidate
    if set(selected) != set(capacities):
        raise ValueError(f"Selected {tool} candidates do not cover all declared capacities")
    return selected


def _rows(candidate: dict[str, Any], count: int, budget: int) -> dict[str, dict[str, Any]]:
    rows = candidate.get("per_query")
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("Selected candidate has incomplete per-query results")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Per-query results must be objects")
        identifier = _name(row.get("query_id"), "query_id")
        if identifier in result:
            raise ValueError(f"Duplicate query_id: {identifier}")
        for label in ("query", "language", "category"):
            _name(row.get(label), label)
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"Query {identifier} requires source evidence")
        canonical = []
        for span in evidence:
            if not isinstance(span, dict):
                raise ValueError("Evidence spans must be objects")
            source = _name(span.get("source_id"), "Evidence source_id")
            start, end = span.get("start"), span.get("end")
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                raise ValueError("Evidence requires a nonempty canonical byte interval")
            canonical.append((source, start, end))
        used = row.get("budget_used")
        if type(used) is not int or not 0 <= used <= budget:
            raise ValueError(f"Query {identifier} violates the retrieved context budget")
        scores = row.get("evidence_at_budget")
        if not isinstance(scores, dict):
            raise ValueError("Query requires evidence_at_budget scores")
        for metric in _METRICS:
            value = scores.get(metric)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                raise ValueError(f"Invalid evidence_at_budget.{metric} score")
        result[identifier] = {**row, "canonical_evidence": tuple(sorted(set(canonical)))}
    return result


def _signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return row["query"], row["language"], row["category"], row["canonical_evidence"]


def _clusters(rows: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Queries sharing any gold source belong to one transitive cluster."""
    parents: dict[str, str] = {}

    def root(source: str) -> str:
        parents.setdefault(source, source)
        while parents[source] != source:
            parents[source] = parents[parents[source]]
            source = parents[source]
        return source

    for row in rows.values():
        sources = [span[0] for span in row["canonical_evidence"]]
        for source in sources[1:]:
            first, other = root(sources[0]), root(source)
            parents[max(first, other)] = min(first, other)
    return {identifier: root(row["canonical_evidence"][0][0]) for identifier, row in rows.items()}


def _percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _slice(
    identifiers: list[str],
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    clusters: dict[str, str],
    samples: int,
    seed: int,
) -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for identifier in identifiers:
        grouped[clusters[identifier]].append(identifier)
    groups = [grouped[key] for key in sorted(grouped)]
    rng = random.Random(seed)
    draws = [[rng.randrange(len(groups)) for _ in groups] for _ in range(samples)]
    metrics = {}
    for metric in _METRICS:
        before = [float(baseline[key]["evidence_at_budget"][metric]) for key in identifiers]
        after = [float(candidate[key]["evidence_at_budget"][metric]) for key in identifiers]
        deltas = {
            key: float(candidate[key]["evidence_at_budget"][metric])
            - float(baseline[key]["evidence_at_budget"][metric])
            for key in identifiers
        }
        group_sums = [sum(deltas[key] for key in group) for group in groups]
        interval = None
        if len(groups) >= 2:
            bootstraps = sorted(
                sum(group_sums[index] for index in draw) / sum(len(groups[index]) for index in draw)
                for draw in draws
            )
            interval = [_percentile(bootstraps, 0.025), _percentile(bootstraps, 0.975)]
        metrics[metric] = {
            "baseline_mean": sum(before) / len(before),
            "candidate_mean": sum(after) / len(after),
            "mean_delta": sum(deltas.values()) / len(deltas),
            "wins": sum(value > _TOLERANCE for value in deltas.values()),
            "ties": sum(abs(value) <= _TOLERANCE for value in deltas.values()),
            "losses": sum(value < -_TOLERANCE for value in deltas.values()),
            "bootstrap_delta_ci_95": interval,
        }
    return {"queries": len(identifiers), "gold_source_clusters": len(groups), "metrics": metrics}


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    baseline_tool: str = "omnichunk",
    candidate_tool: str = "omnichunk",
    bootstrap_samples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """Fail closed when report provenance, selected coverage or gold labels differ."""
    for report in (baseline, candidate):
        if not isinstance(report, dict):
            raise ValueError("Reports must be JSON objects")
        _validate_json(report)
    _positive(bootstrap_samples, "Bootstrap sample count")
    if type(seed) is not int:
        raise ValueError("Bootstrap seed must be an integer")
    digest = _name(baseline.get("corpus_manifest_sha256"), "Corpus manifest SHA-256")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Corpus manifest fingerprint must be a lowercase SHA-256 digest")
    if digest != candidate.get("corpus_manifest_sha256"):
        raise ValueError("Corpus manifest fingerprints differ")
    before, after = _selected(baseline, baseline_tool), _selected(candidate, candidate_tool)
    left, right = baseline["configuration"], candidate["configuration"]
    for key in _CONFIG:
        if (
            key not in left
            or key not in right
            or (type(left[key]) is not type(right[key]) or left[key] != right[key])
        ):
            raise ValueError(f"Frozen experiment configuration differs or is missing: {key}")
    if set(before) != set(after):
        raise ValueError("Chunk capacity sets differ")
    model = None
    if left["retriever"] == "frozen-dense-cosine-v1":
        model = _dense_contract(left)
        if model != _dense_contract(right):
            raise ValueError("Dense model/encoder contracts differ")
    count = _positive(baseline.get("queries"), "Report query count")
    if _positive(candidate.get("queries"), "Candidate query count") != count:
        raise ValueError("Report query counts differ")
    budget = _positive(left["retrieval_budget"], "Retrieval budget")
    comparisons = []
    reference = None
    for capacity in sorted(before):
        baseline_rows = _rows(before[capacity], count, budget)
        candidate_rows = _rows(after[capacity], count, budget)
        signatures = {key: _signature(value) for key, value in baseline_rows.items()}
        if signatures != {key: _signature(value) for key, value in candidate_rows.items()}:
            raise ValueError("Paired query IDs, texts, labels or gold evidence differ")
        if reference is not None and signatures != reference:
            raise ValueError("Query labels differ between chunk capacities")
        reference = signatures
        clusters = _clusters(baseline_rows)
        slices: dict[str, list[str]] = defaultdict(list)
        for identifier, row in sorted(baseline_rows.items()):
            slices["all"].append(identifier)
            slices[f"language:{row['language']}"].append(identifier)
            slices[f"category:{row['category']}"].append(identifier)
        comparisons.append(
            {
                "chunk_capacity": capacity,
                "slices": {
                    name: _slice(
                        ids, baseline_rows, candidate_rows, clusters, bootstrap_samples, seed
                    )
                    for name, ids in sorted(slices.items())
                },
            }
        )
    return {
        "schema_version": 1,
        "corpus_manifest_sha256": digest,
        "baseline_tool": baseline_tool,
        "candidate_tool": candidate_tool,
        "configuration": {key: left[key] for key in _CONFIG},
        "dense_model_contract": model,
        "bootstrap": {
            "samples": bootstrap_samples,
            "seed": seed,
            "unit": "connected components of gold source IDs",
            "interval": "95% percentile interval for paired query-mean delta",
        },
        "interpretation": (
            "Descriptive paired evidence scores, not a universal ranking. Intervals assume "
            "independent gold-source components; queries within a component stay together. "
            "Sources from the same article or organization may remain correlated. Small "
            "samples and configuration/slice selection limit inference; intervals are not "
            "adjusted for multiple comparisons. Fewer than two source clusters yields no interval. "
            "Wins/ties/losses use an absolute delta tolerance of 1e-12."
        ),
        "comparisons": comparisons,
    }


def load_report(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = gzip.decompress(raw) if path.suffix == ".gz" else raw
    report = json.loads(payload, object_pairs_hook=_pairs)
    _validate_json(report)
    return report, hashlib.sha256(payload).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-tool", default="omnichunk")
    parser.add_argument("--candidate-tool", default="omnichunk")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        baseline, baseline_hash = load_report(args.baseline)
        candidate, candidate_hash = load_report(args.candidate)
        report = compare_reports(
            baseline,
            candidate,
            baseline_tool=args.baseline_tool,
            candidate_tool=args.candidate_tool,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        report["reports"] = {"baseline_sha256": baseline_hash, "candidate_sha256": candidate_hash}
        payload = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
    except (ValueError, OSError, TypeError, zlib.error) as exc:
        print(f"Paired retrieval comparison failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
