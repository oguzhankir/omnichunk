"""Unit integrity checks only; toy vectors here are never quality evidence."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FROZEN = Path(
    os.environ.get("OMNICHUNK_FROZEN_HARNESS", Path(__file__).parent / "frozen-candidate")
).resolve()
sys.path.insert(0, str(FROZEN))
sys.path.insert(0, str(FROZEN / "src"))
from extend_dense_vectors import (  # noqa: E402
    INPUT_POLICY,
    PIPELINE,
    CachedEncoder,
    read_prior,
    validate_prior,
)

from benchmarks.retrieval import dense  # noqa: E402

assert Path(dense.__file__).resolve().is_relative_to(FROZEN)


def prior():
    return {
        "schema_version": 1,
        "corpus_manifest_sha256": "a" * 64,
        "model_id": "unit-test",
        "model_revision": "frozen-unit-v1",
        "preprocessing_revision": "unit-preprocess-v1",
        "dimension": 2,
        "overflow_policy": "error",
        "records": [
            {"role": role, "text_sha256": dense.text_sha256("same"), "vector": vector}
            for role, vector in [("passage", [1.25, -0.0]), ("query", [2.5, 3.0])]
        ],
        "producer_metadata": {
            "model_files": {"model.bin": "b" * 64},
            "packages": {"unit": "1"},
            "prompt": "",
            "include_special_tokens": True,
            "max_sequence_length": 64,
            "input_policy": INPUT_POLICY,
            "supported_pipeline": PIPELINE,
            "normalization": "cosine normalization during evaluation",
            "device": "cpu",
            "producer_source_sha256": "c" * 64,
            "cpu_threads_requested": 2,
            "torch_threads": {"intraop": 2, "interop": 2},
            "input_statistics": {"maximum_input_tokens": 6, "encoded_texts": 2},
            "role_statistics": {"passage": {"unique_texts": 1}, "query": {"unique_texts": 1}},
        },
    }


def validate(data, **overrides):
    args = dict(
        corpus_sha="a" * 64,
        model_id="unit-test",
        model_revision="frozen-unit-v1",
        preprocessing_revision="unit-preprocess-v1",
        files={"model.bin": "b" * 64},
        packages={"unit": "1"},
        producer_sha="c" * 64,
        limit=64,
    )
    args.update(overrides)
    validate_prior(data, **args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("corpus_manifest_sha256", "d" * 64),
        ("model_id", "wrong-model"),
        ("model_revision", "wrong-revision"),
        ("preprocessing_revision", "wrong-preprocess"),
        ("overflow_policy", "truncate"),
    ],
)
def test_cache_experiment_identity_mismatch_is_rejected(field, value):
    data = prior()
    data[field] = value
    with pytest.raises(ValueError, match=field):
        validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_files", {"model.bin": "e" * 64}),
        ("packages", {"unit": "2"}),
        ("prompt", "changed"),
        ("include_special_tokens", False),
        ("max_sequence_length", 32),
        ("input_policy", "truncate"),
        ("supported_pipeline", "custom"),
        ("producer_source_sha256", "d" * 64),
        ("torch_threads", {"intraop": 1, "interop": 1}),
    ],
)
def test_cache_producer_mismatch_is_rejected(field, value):
    data = prior()
    data["producer_metadata"][field] = value
    with pytest.raises(ValueError, match=field):
        validate(data)


def test_valid_frozen_contract_and_role_cardinality():
    data = prior()
    validate(data)
    data["records"] = data["records"][:1]
    data["producer_metadata"]["input_statistics"]["encoded_texts"] = 1
    with pytest.raises(ValueError, match="query role"):
        validate(data)


def test_committed_artifact_sha_role_digest_and_missing_file_checks(tmp_path):
    path = tmp_path / "prior.json"
    raw = json.dumps(prior()).encode()
    path.write_bytes(raw)
    api = SimpleNamespace(dense=dense)
    assert read_prior(path, hashlib.sha256(raw).hexdigest(), api) == prior()
    with pytest.raises(ValueError, match="SHA-256"):
        read_prior(path, "0" * 64, api)
    with pytest.raises(FileNotFoundError):
        read_prior(tmp_path / "missing.json", "0" * 64, api)
    bad = prior()
    bad["records"][0]["role"] = "document"
    raw = json.dumps(bad).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="role"):
        read_prior(path, hashlib.sha256(raw).hexdigest(), api)
    bad = prior()
    bad["records"][0]["text_sha256"] = "invalid"
    raw = json.dumps(bad).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="text_sha256"):
        read_prior(path, hashlib.sha256(raw).hexdigest(), api)


class Array:
    def __init__(self, rows):
        self.rows = rows

    def tolist(self):
        return self.rows


class UnitModel:
    def __init__(self):
        self.calls = []
        self.change_native = False
        self.fail = False

    def tokenizer(self, texts, **kwargs):
        assert kwargs == dict(truncation=False, add_special_tokens=True, padding=False)
        return {"input_ids": [[101, *text.encode("utf-8"), 102] for text in texts]}

    def tokenize(self, texts):
        rows = self.tokenizer(texts, truncation=False, add_special_tokens=True, padding=False)[
            "input_ids"
        ]
        if self.change_native:
            rows[0] = rows[0][:-1]
        return {"input_ids": Array(rows), "attention_mask": Array([[1] * len(row) for row in rows])}

    def encode(self, texts, **kwargs):
        self.calls.append(texts)
        assert kwargs["prompt"] == "" and kwargs["normalize_embeddings"] is False
        if self.fail:
            raise RuntimeError("unit encoder failed")
        return Array([[float(len(text)), 1.0] for text in texts])


def cache(records=None, model=None):
    return CachedEncoder(
        records if records is not None else prior()["records"],
        model=model or UnitModel(),
        limit=64,
        batch_size=32,
        text_sha=dense.text_sha256,
        metadata={"unit_test_only": True},
    )


def test_exact_role_and_text_key_reuse_preserves_raw_vector_values():
    encoder = cache()
    assert encoder("passage", ["same", "new"]) == [[1.25, -0.0], [3.0, 1.0]]
    assert encoder.model.calls == [["new"]]
    assert encoder("query", ["same"]) == [[2.5, 3.0]]
    assert encoder.stats["passage"]["reused_texts"] == 1
    assert encoder.stats["passage"]["new_texts"] == 1
    assert encoder.stats["query"]["encoder_calls"] == 0
    query_only = cache(records=[prior()["records"][1]])
    assert query_only("passage", ["same"]) == [[4.0, 1.0]]
    assert query_only.model.calls == [["same"]]


def test_cached_inputs_still_reject_overflow_and_changed_native_ids():
    encoder = cache()
    with pytest.raises(ValueError, match="token limit"):
        encoder("passage", ["x" * 65])
    model = UnitModel()
    model.change_native = True
    with pytest.raises(ValueError, match="token IDs"):
        cache(model=model)("passage", ["same"])
    with pytest.raises(ValueError, match="role"):
        cache()("wrong", ["same"])


def test_artifact_builder_preserves_cache_bytes_and_only_encodes_misses(tmp_path):
    encoder = cache()
    path = tmp_path / "extended.json"
    dense.build_dense_artifact(
        path,
        corpus_manifest_sha256="a" * 64,
        model_id="unit-test",
        model_revision="frozen-unit-v1",
        preprocessing_revision="unit-preprocess-v1",
        passages=["same", "new", "same"],
        queries=["same"],
        embed=encoder,
        batch_size=32,
        producer_metadata=encoder.metadata,
    )
    actual = json.loads(path.read_text())
    old = {(r["role"], r["text_sha256"]): r for r in prior()["records"]}
    for record in actual["records"]:
        key = record["role"], record["text_sha256"]
        if key in old:
            assert json.dumps(record["vector"]).encode() == json.dumps(old[key]["vector"]).encode()
    assert encoder.model.calls == [["new"]]
    assert len(actual["records"]) == 3
    assert actual["producer_metadata"]["actual_encoder_work"]["passage"]["new_texts"] == 1
    frozen = dense.FrozenDenseRetriever(path, corpus_manifest_sha256="a" * 64)
    assert frozen._vector("query", "same")
    with pytest.raises(ValueError, match="Missing frozen"):
        frozen._vector("query", "new")


def test_missing_cache_encoder_failure_does_not_replace_existing_artifact(tmp_path):
    model = UnitModel()
    model.fail = True
    encoder = cache(model=model)
    path = tmp_path / "out.json"
    path.write_text("sentinel")
    with pytest.raises(RuntimeError, match="unit encoder failed"):
        dense.build_dense_artifact(
            path,
            corpus_manifest_sha256="a" * 64,
            model_id="unit-test",
            model_revision="frozen-unit-v1",
            preprocessing_revision="unit-preprocess-v1",
            passages=["uncached"],
            queries=["same"],
            embed=encoder,
        )
    assert path.read_text() == "sentinel"


@pytest.mark.parametrize(
    "statistics",
    [
        {"maximum_input_tokens": 65, "encoded_texts": 2},
        {"maximum_input_tokens": 6, "encoded_texts": 3},
    ],
)
def test_prior_overflow_and_total_cardinality_claims_must_match_records(statistics):
    data = prior()
    data["producer_metadata"]["input_statistics"] = statistics
    with pytest.raises(ValueError):
        validate(data)


def test_all_cache_misses_cannot_change_the_trusted_vector_dimension(tmp_path):
    class WrongDimensionModel(UnitModel):
        def encode(self, texts, **kwargs):
            return Array([[1.0, 2.0, 3.0] for text in texts])

    encoder = cache(model=WrongDimensionModel())
    path = tmp_path / "wrong.json"
    with pytest.raises(ValueError, match="dimension differs"):
        dense.build_dense_artifact(
            path,
            corpus_manifest_sha256="a" * 64,
            model_id="unit-test",
            model_revision="frozen-unit-v1",
            preprocessing_revision="unit-preprocess-v1",
            passages=["never cached passage"],
            queries=["never cached query"],
            embed=encoder,
        )
    assert not path.exists()
