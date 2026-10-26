from __future__ import annotations

import gzip
import json
from copy import deepcopy

import pytest

from benchmarks import compare_retrieval as comparison


def report(scores=(0.0, 0.0, 0.0, 1.0), *, dense=False):
    rows = []
    for index, value in enumerate(scores):
        sources = (("a",), ("a", "b"), ("b",), ("c",))[index]
        rows.append(
            {
                "query_id": f"q{index}",
                "query": f"Question {index}",
                "language": "en" if index < 3 else "tr",
                "category": "prose",
                "evidence": [{"source_id": source, "start": 0, "end": 3} for source in sources],
                "budget_used": 20,
                "evidence_at_budget": {key: value for key in ("precision", "recall", "iou")},
            }
        )
    configuration = {
        "split": "dev",
        "unit": "tokens",
        "tokenizer": "frozen-tokenizer-v1",
        "retrieval_budget": 100,
        "top_k": 5,
        "context": "none",
        "overlap": 0,
        "retriever": "frozen-dense-cosine-v1" if dense else "lexical-test-v1",
        "idf_fit": None if dense else "source documents only",
        "relevance": "span intersection",
        "budget_selection": "whole ranked prefix",
        "chunk_sizes": [64],
    }
    if dense:
        configuration["dense_embeddings"] = {
            "model_id": "encoder",
            "model_revision": "abc123",
            "dimension": 4,
            "preprocessing_revision": "identity-v1",
            "artifact_sha256": "a" * 64,
            "producer_metadata": {
                "model_files": {"weights": "b" * 64},
                "packages": {"encoder": "1.0"},
                "prompt": "",
                "max_sequence_length": 128,
                "supported_pipeline": "standard Transformer + mean Pooling",
                "input_statistics": {"encoded_texts": 20},
            },
        }
    return {
        "schema_version": 2,
        "corpus_manifest_sha256": "c" * 64,
        "configuration": configuration,
        "queries": 4,
        "candidates": [
            {"tool": "omnichunk", "chunk_capacity": 64, "status": "ok", "per_query": rows}
        ],
    }


def test_paired_bootstrap_preserves_transitively_connected_gold_sources():
    before, after = report(), report((1.0, 1.0, 1.0, 0.0))
    result = comparison.compare_reports(before, after)
    overall = result["comparisons"][0]["slices"]["all"]
    assert overall["queries"] == 4
    assert overall["gold_source_clusters"] == 2
    recall = overall["metrics"]["recall"]
    assert recall["mean_delta"] == 0.5
    assert (recall["wins"], recall["ties"], recall["losses"]) == (3, 0, 1)
    assert recall["bootstrap_delta_ci_95"] == [-1.0, 1.0]
    # Three English questions share a source cluster; query-level bootstrap would
    # give spurious precision. A one-cluster slice deliberately has no interval.
    english = result["comparisons"][0]["slices"]["language:en"]
    assert english["gold_source_clusters"] == 1
    assert english["metrics"]["recall"]["bootstrap_delta_ci_95"] is None
    assert result == comparison.compare_reports(before, after)


def test_artifact_hash_and_input_counts_can_change_with_candidate_boundaries():
    before, after = report(dense=True), report(dense=True)
    metadata = after["configuration"]["dense_embeddings"]
    metadata["artifact_sha256"] = "d" * 64
    metadata["producer_metadata"]["input_statistics"]["encoded_texts"] = 99
    result = comparison.compare_reports(before, after)
    assert result["comparisons"][0]["slices"]["all"]["metrics"]["iou"]["mean_delta"] == 0


@pytest.mark.parametrize(
    "field", ["model_id", "model_revision", "preprocessing_revision", "dimension"]
)
def test_different_dense_model_contracts_are_not_comparable(field):
    before, after = report(dense=True), report(dense=True)
    after["configuration"]["dense_embeddings"][field] = 8 if field == "dimension" else "changed"
    with pytest.raises(ValueError, match="contracts differ"):
        comparison.compare_reports(before, after)


@pytest.mark.parametrize(
    "field", ["model_files", "packages", "prompt", "max_sequence_length", "supported_pipeline"]
)
def test_different_encoder_processing_or_weights_are_not_comparable(field):
    before, after = report(dense=True), report(dense=True)
    metadata = after["configuration"]["dense_embeddings"]["producer_metadata"]
    metadata[field] = (
        {"other": "d" * 64}
        if field in ("model_files", "packages")
        else (64 if field == "max_sequence_length" else "changed")
    )
    with pytest.raises(ValueError, match="contracts differ"):
        comparison.compare_reports(before, after)


def test_missing_dense_snapshot_provenance_fails_instead_of_attesting_equal_models():
    before, after = report(dense=True), report(dense=True)
    for item in (before, after):
        item["configuration"]["dense_embeddings"]["producer_metadata"] = {}
    with pytest.raises(ValueError, match="model_files"):
        comparison.compare_reports(before, after)


@pytest.mark.parametrize(
    "field,value",
    [
        ("split", "test"),
        ("unit", "chars"),
        ("tokenizer", "other"),
        ("retrieval_budget", 200),
        ("top_k", 3),
        ("context", "rendered"),
        ("overlap", 0.0),
        ("retriever", "other"),
        ("budget_selection", "skip overflow"),
    ],
)
def test_mixed_experiment_settings_fail(field, value):
    before, after = report(), report()
    after["configuration"][field] = value
    with pytest.raises(ValueError, match="configuration differs"):
        comparison.compare_reports(before, after)


@pytest.mark.parametrize(
    "change", ["missing", "failed", "duplicate", "partial", "wrong_count", "duplicate_query"]
)
def test_incomplete_or_ambiguous_selected_candidate_fails(change):
    before, after = report(), report()
    candidate = after["candidates"][0]
    if change == "missing":
        after["candidates"] = []
    elif change == "failed":
        candidate["status"] = "error"
    elif change == "duplicate":
        after["candidates"].append(deepcopy(candidate))
    elif change == "partial":
        candidate["per_query"].pop()
    elif change == "wrong_count":
        after["queries"] = 3
    else:
        candidate["per_query"][1]["query_id"] = "q0"
    with pytest.raises(ValueError):
        comparison.compare_reports(before, after)


@pytest.mark.parametrize(
    "field,value",
    [
        ("query_id", "changed"),
        ("query", "Other question"),
        ("language", "ja"),
        ("category", "code"),
        ("evidence", [{"source_id": "a", "start": 1, "end": 3}]),
    ],
)
def test_changed_paired_query_texts_labels_or_evidence_fail(field, value):
    before, after = report(), report()
    after["candidates"][0]["per_query"][0][field] = value
    with pytest.raises(ValueError, match="gold evidence differ"):
        comparison.compare_reports(before, after)


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_scores_fail(score):
    before, after = report(), report()
    after["candidates"][0]["per_query"][0]["evidence_at_budget"]["recall"] = score
    with pytest.raises(ValueError):
        comparison.compare_reports(before, after)


def test_over_budget_context_and_different_corpus_are_rejected():
    before, after = report(), report()
    after["candidates"][0]["per_query"][0]["budget_used"] = 101
    with pytest.raises(ValueError, match="context budget"):
        comparison.compare_reports(before, after)
    after = report()
    after["corpus_manifest_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="fingerprints differ"):
        comparison.compare_reports(before, after)


def test_selected_competitor_can_be_paired_without_unavailable_unrelated_tools():
    before, after = report(), report((0.5, 0.5, 0.5, 1.0))
    after["candidates"][0]["tool"] = "competitor"
    after["candidates"].append(
        {"tool": "uninstalled", "chunk_capacity": 64, "status": "unavailable"}
    )
    result = comparison.compare_reports(before, after, candidate_tool="competitor")
    assert result["candidate_tool"] == "competitor"


def test_cli_reads_gzip_preserves_report_fingerprints_and_writes_json(tmp_path):
    baseline, candidate = tmp_path / "before.json", tmp_path / "after.json.gz"
    baseline.write_text(json.dumps(report()))
    candidate.write_bytes(gzip.compress(json.dumps(report()).encode()))
    output = tmp_path / "comparison.json"
    assert (
        comparison.main(
            [
                "--baseline",
                str(baseline),
                "--candidate",
                str(candidate),
                "--bootstrap-samples",
                "200",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text())
    assert data["reports"]["baseline_sha256"] == data["reports"]["candidate_sha256"]
    assert data["bootstrap"]["samples"] == 200


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'])
def test_cli_rejects_ambiguous_or_nonfinite_json(tmp_path, capsys, text):
    bad = tmp_path / "bad.json"
    bad.write_text(text)
    assert comparison.main(["--baseline", str(bad), "--candidate", str(bad)]) == 2
    assert "Paired retrieval comparison failed" in capsys.readouterr().err


def test_query_labels_must_remain_fixed_across_capacities():
    before, after = report(), report()
    for item in (before, after):
        item["configuration"]["chunk_sizes"] = [64, 96]
        other = deepcopy(item["candidates"][0])
        other["chunk_capacity"] = 96
        other["per_query"][0]["language"] = "ja"
        item["candidates"].append(other)
    with pytest.raises(ValueError, match="between chunk capacities"):
        comparison.compare_reports(before, after)


def test_failed_comparison_does_not_replace_existing_output(tmp_path):
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(report()))
    different = report()
    different["configuration"]["split"] = "test"
    after.write_text(json.dumps(different))
    output = tmp_path / "comparison.json"
    output.write_text("preserve previous result")
    assert (
        comparison.main(
            ["--baseline", str(before), "--candidate", str(after), "--output", str(output)]
        )
        == 2
    )
    assert output.read_text() == "preserve previous result"


def test_special_token_budget_policy_must_match():
    before, after = report(), report()
    before["configuration"]["include_special_tokens"] = False
    after["configuration"]["include_special_tokens"] = True
    with pytest.raises(ValueError, match="configuration differs.*include_special_tokens"):
        comparison.compare_reports(before, after)


def test_legacy_missing_special_token_policy_matches_explicit_content_only():
    before, after = report(), report()
    after["configuration"]["include_special_tokens"] = False
    result = comparison.compare_reports(before, after)
    assert result["configuration"]["include_special_tokens"] is False
    assert "include_special_tokens" not in before["configuration"]


@pytest.mark.parametrize("invalid", [None, 0, 1, "false", "true"])
def test_special_token_policy_requires_a_boolean(invalid):
    before, after = report(), report()
    for item in (before, after):
        item["configuration"]["include_special_tokens"] = invalid
    with pytest.raises(ValueError, match="include_special_tokens must be a boolean"):
        comparison.compare_reports(before, after)


def test_matching_special_token_policy_is_preserved_in_output():
    before, after = report(), report()
    for item in (before, after):
        item["configuration"]["include_special_tokens"] = True
    result = comparison.compare_reports(before, after)
    assert result["configuration"]["include_special_tokens"] is True
