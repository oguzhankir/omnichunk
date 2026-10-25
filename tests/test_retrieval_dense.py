from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.retrieval.adapters import Passage
from benchmarks.retrieval.dense import FrozenDenseRetriever, build_dense_artifact, text_sha256

MANIFEST = "a" * 64


def artifact(tmp_path: Path, **kwargs):
    path = tmp_path / "vectors.json"
    build_dense_artifact(
        path,
        corpus_manifest_sha256=MANIFEST,
        model_id="test-encoder",
        model_revision="frozen-v1",
        preprocessing_revision="identity-v1",
        passages=["same", "opposite", "orthogonal"],
        queries=["question", "same"],
        embed=lambda role, texts: [
            {
                "same": [3.0, 0.0],
                "opposite": [-4.0, 0.0],
                "orthogonal": [0.0, 9.0],
                "question": [2.0, 0.0],
            }[text]
            if role == "passage" or text == "question"
            else [-1.0, 0.0]
            for text in texts
        ],
        **kwargs,
    )
    return path


def passage(identifier, text):
    return Passage(identifier, "source", 0, len(text.encode()), text)


def test_cosine_normalization_negative_scores_and_role_specific_vectors(tmp_path):
    path = artifact(tmp_path)
    retriever = FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)
    passages = [
        passage("negative", "opposite"),
        passage("positive", "same"),
        passage("zero", "orthogonal"),
        passage("positive-a", "same"),
    ]
    index = retriever.index(passages)
    ranked = index.rank("question")
    assert [(p.passage_id, score) for p, score in ranked] == [
        ("positive", 1.0),
        ("positive-a", 1.0),
        ("zero", 0.0),
        ("negative", -1.0),
    ]
    assert index.rank("same")[0][0].passage_id == "negative"
    assert retriever.embedding_calls == 0
    assert retriever.metadata["artifact_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = retriever.metadata
    metadata["model_id"] = "mutated"
    assert retriever.metadata["model_id"] == "test-encoder"
    with pytest.raises(TypeError):
        retriever.vectors[("query", text_sha256("question"))] = (9.0,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("dimension", True),
        ("dimension", 0),
        ("corpus_manifest_sha256", "bad"),
        ("model_id", ""),
        ("model_revision", "main"),
        ("preprocessing_revision", "latest"),
        ("overflow_policy", "truncate"),
        ("records", []),
        ("producer_metadata", []),
        ("producer_metadata", {"bad": float("nan")}),
    ],
)
def test_invalid_artifact_contract_rejected(tmp_path, field, value):
    path = artifact(tmp_path)
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(vector=[float("nan"), 0]),
        lambda r: r.update(vector=[float("inf"), 0]),
        lambda r: r.update(vector=[True, 0]),
        lambda r: r.update(vector=[0, 0]),
        lambda r: r.update(vector=[1]),
        lambda r: r.update(vector=[10**400, 1]),
        lambda r: r.update(role="document"),
        lambda r: r.update(text_sha256="not-a-digest"),
        lambda r: r.update(extra="unknown"),
    ],
)
def test_invalid_embedding_records_rejected(tmp_path, change):
    path = artifact(tmp_path)
    data = json.loads(path.read_text())
    change(data["records"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)


def test_duplicate_records_and_duplicate_json_fields_rejected(tmp_path):
    path = artifact(tmp_path)
    original = path.read_text()
    data = json.loads(original)
    data["records"].append(data["records"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate embedding role"):
        FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)
    path.write_text(
        original.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    )
    with pytest.raises(ValueError, match="Duplicate embedding artifact field"):
        FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"corpus_manifest_sha256": "b" * 64},
        {"model_id": "other"},
        {"model_revision": "v2"},
        {"preprocessing_revision": "other-v1"},
    ],
)
def test_experiment_contract_mismatch_rejected(tmp_path, kwargs):
    expected = {"corpus_manifest_sha256": MANIFEST, **kwargs}
    with pytest.raises(ValueError, match="does not match"):
        FrozenDenseRetriever(artifact(tmp_path), **expected)


def test_missing_text_fails_instead_of_silently_embedding_or_skipping(tmp_path):
    retriever = FrozenDenseRetriever(artifact(tmp_path), corpus_manifest_sha256=MANIFEST)
    with pytest.raises(ValueError, match="Missing frozen embedding for passage"):
        retriever.index([passage("a", "same ")])
    index = retriever.index([passage("a", "same")])
    with pytest.raises(ValueError, match="Missing frozen embedding for query"):
        index.rank("Question")
    with pytest.raises(ValueError, match="Duplicate passage IDs"):
        retriever.index([passage("a", "same"), passage("a", "opposite")])


def test_builder_batches_deduplicates_roles_and_records_real_provider_calls(tmp_path):
    calls = []

    def encode(role, texts):
        calls.append((role, texts))
        return [[1.0, 0.0] for _ in texts]

    path = tmp_path / "vectors.json"
    result = build_dense_artifact(
        path,
        corpus_manifest_sha256=MANIFEST,
        model_id="test",
        model_revision="v1",
        preprocessing_revision="identity-v1",
        passages=["a", "b", "a"],
        queries=["a", "a"],
        embed=encode,
        batch_size=1,
        producer_metadata={"files": {"model.bin": "hash"}, "max_sequence_length": 512},
    )
    assert result["embedding_calls"] == len(calls) == 3
    assert result["records"] == 3
    retriever = FrozenDenseRetriever(path, corpus_manifest_sha256=MANIFEST)
    assert retriever.metadata["producer_metadata"]["max_sequence_length"] == 512


@pytest.mark.parametrize("vectors", [[[1.0, 0.0]], [[1.0, 0.0], [0.0, 0.0]], [[1.0, 0.0], [1.0]]])
def test_failed_builder_preserves_existing_artifact(tmp_path, vectors):
    path = tmp_path / "vectors.json"
    path.write_text("original")
    with pytest.raises(ValueError):
        build_dense_artifact(
            path,
            corpus_manifest_sha256=MANIFEST,
            model_id="test",
            model_revision="v1",
            preprocessing_revision="identity-v1",
            passages=["a", "b"],
            queries=[],
            embed=lambda role, texts: vectors,
        )
    assert path.read_text() == "original"
