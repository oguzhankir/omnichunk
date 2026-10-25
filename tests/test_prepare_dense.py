from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks import prepare_dense
from benchmarks.retrieval.dense import FrozenDenseRetriever


class FakeTokenizer:
    model_max_length = 512

    def __call__(self, texts, **kwargs):
        assert kwargs == {"truncation": False, "add_special_tokens": True, "padding": False}
        return {"input_ids": [[0] * (len(text) + 2) for text in texts]}


class Vectors(list):
    def tolist(self):
        return list(self)


class FakeModel:
    max_seq_length = 512
    tokenizer = FakeTokenizer()

    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        assert kwargs["prompt"] == ""
        assert kwargs["normalize_embeddings"] is False
        self.calls.append(texts)
        return Vectors([[1.0, float(len(text))] for text in texts])

    def tokenize(self, texts):
        rows = self.tokenizer(texts, truncation=False, add_special_tokens=True, padding=False)[
            "input_ids"
        ]
        return {
            "input_ids": Vectors(rows),
            "attention_mask": Vectors([[1] * len(row) for row in rows]),
        }


def configuration(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"local": true}')
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    documents, queries = [], []
    for index, (text, question, split) in enumerate(
        [
            ("Backups expire after thirty days.", "When do backups expire?", "dev"),
            ("Logs expire after ninety days.", "When do logs expire?", "test"),
        ]
    ):
        source = f"document-{index}"
        raw = text.encode()
        (corpus / f"{source}.txt").write_bytes(raw)
        documents.append(
            {
                "source_id": source,
                "path": f"{source}.txt",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "language": "en",
                "category": "text",
                "split": split,
            }
        )
        queries.append(
            {
                "query_id": f"q-{index}",
                "text": question,
                "split": split,
                "evidence": [{"source_id": source, "start": 0, "end": len(raw), "quote": text}],
            }
        )
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "small-v1",
                "license": "MIT",
                "documents": documents,
                "queries": queries,
            }
        )
    )
    output = tmp_path / "dense.json"
    command = [
        "--corpus",
        str(corpus),
        "--tools",
        "fixed",
        "--chunk-sizes",
        "12",
        "--model-dir",
        str(model_dir),
        "--model-id",
        "test-local-model",
        "--model-revision",
        "frozen-v1",
        "--output",
        str(output),
    ]
    return command, model_dir, output, corpus


def test_prepare_local_model_records_fingerprints_and_rejects_downloads(
    tmp_path, monkeypatch, capsys
):
    command, directory, output, corpus = configuration(tmp_path)
    model = FakeModel()

    def load(path):
        assert path == directory
        return model

    monkeypatch.setattr(prepare_dense, "_load_model", load)
    assert prepare_dense.main(command) == 0
    summary = json.loads(capsys.readouterr().out)
    retriever = FrozenDenseRetriever(
        output,
        corpus_manifest_sha256=hashlib.sha256((corpus / "manifest.json").read_bytes()).hexdigest(),
    )
    metadata = retriever.metadata["producer_metadata"]
    assert metadata["model_files"] == {
        "config.json": hashlib.sha256((directory / "config.json").read_bytes()).hexdigest()
    }
    assert metadata["device"] == "cpu"
    assert metadata["input_statistics"]["encoded_texts"] == summary["encoded_texts"]
    assert all("Logs" not in text for batch in model.calls for text in batch)


def test_overflow_fails_before_encoding_and_preserves_artifact(tmp_path, monkeypatch, capsys):
    command, _, output, _ = configuration(tmp_path)
    output.write_text("old")
    model = FakeModel()
    model.max_seq_length = 5
    monkeypatch.setattr(prepare_dense, "_load_model", lambda _: model)
    assert prepare_dense.main(command) == 2
    assert "truncated comparisons are forbidden" in capsys.readouterr().err
    assert not model.calls
    assert output.read_text() == "old"


def test_model_snapshot_mutation_during_encoding_preserves_artifact(tmp_path, monkeypatch, capsys):
    command, directory, output, _ = configuration(tmp_path)
    output.write_text("old")
    model = FakeModel()
    original = model.encode

    def encode(texts, **kwargs):
        (directory / "weights.bin").write_bytes(b"changed")
        return original(texts, **kwargs)

    model.encode = encode
    monkeypatch.setattr(prepare_dense, "_load_model", lambda _: model)
    assert prepare_dense.main(command) == 2
    assert "changed while encoding" in capsys.readouterr().err
    assert output.read_text() == "old"


def test_missing_local_model_reports_actionable_error(tmp_path, capsys):
    command, directory, _, _ = configuration(tmp_path)
    (directory / "config.json").unlink()
    assert prepare_dense.main(command) == 2
    assert "contains no files" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--batch-size", "0"],
        ["--chunk-sizes", "0"],
        ["--tools", "unknown"],
        ["--unit", "tokens", "--tokenizer", "approximate"],
    ],
)
def test_invalid_preparation_configuration_rejected(tmp_path, extra):
    command, _, _, _ = configuration(tmp_path)
    with pytest.raises(SystemExit):
        prepare_dense.main([*command, *extra])


def test_native_preprocessing_difference_is_rejected_before_encode(tmp_path, monkeypatch, capsys):
    command, _, output, _ = configuration(tmp_path)
    output.write_text("old")
    model = FakeModel()
    original = model.tokenize

    def tokenize(texts):
        result = original(texts)
        result["input_ids"][0] = result["input_ids"][0][:-1]
        result["attention_mask"][0] = result["attention_mask"][0][:-1]
        return result

    model.tokenize = tokenize
    monkeypatch.setattr(prepare_dense, "_load_model", lambda _: model)
    assert prepare_dense.main(command) == 2
    assert "preprocessing changes or truncates inputs" in capsys.readouterr().err
    assert output.read_text() == "old"
    assert not model.calls
