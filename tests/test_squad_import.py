from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.import_squad import _import_squad, main
from benchmarks.retrieval.corpus import load_corpus


def _dataset(path: Path) -> str:
    data = {
        "version": "1.1",
        "data": [
            {
                "title": title,
                "paragraphs": [
                    {
                        "context": f"{title}: Café ve çay herkes içindir.",
                        "qas": [
                            {
                                "id": f"{title}-q",
                                "question": f"What drink appears in {title}?",
                                "answers": [
                                    {"answer_start": 0, "text": "invalid"},
                                    {"answer_start": len(title + ": Café ve "), "text": "çay"},
                                ],
                            }
                        ],
                    }
                ],
            }
            for title in ("Article One", "Article Two", "Article Three", "Article Four")
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_import_is_deterministic_article_disjoint_and_byte_exact(tmp_path):
    source = tmp_path / "source.json"
    digest = _dataset(source)
    options = {
        "expected_sha256": digest,
        "articles": 4,
        "paragraphs_per_article": 1,
        "questions_per_paragraph": 1,
    }
    first = tmp_path / "first"
    manifest = _import_squad(source, first, **options)
    second = tmp_path / "second"
    _import_squad(source, second, **options)
    assert {str(p.relative_to(first)): p.read_bytes() for p in first.rglob("*") if p.is_file()} == {
        str(p.relative_to(second)): p.read_bytes() for p in second.rglob("*") if p.is_file()
    }
    corpus = load_corpus(first)
    assert corpus.license == "CC-BY-SA-4.0"
    assert len(corpus.documents) == len(corpus.queries) == 4
    assert {doc.split for doc in corpus.documents} == {"dev", "test"}
    by_id = {doc.source_id: doc for doc in corpus.documents}
    for query in corpus.queries:
        evidence = query.evidence[0]
        doc = by_id[evidence.source_id]
        assert doc.text.encode()[evidence.start : evidence.end].decode() == "çay"
        assert query.split == doc.split
    dev = {doc["article_title"] for doc in manifest["documents"] if doc["split"] == "dev"}
    test = {doc["article_title"] for doc in manifest["documents"] if doc["split"] == "test"}
    assert dev.isdisjoint(test)
    assert manifest["provenance"]["upstream_sha256"] == digest
    assert "ShareAlike" in (first / "LICENSE").read_text()


def test_bad_annotations_and_checksum_leave_output_untouched(tmp_path):
    source = tmp_path / "source.json"
    digest = _dataset(source)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="checksum"):
        _import_squad(source, output, expected_sha256="0" * 64)
    assert not output.exists()
    data = json.loads(source.read_text())
    for article in data["data"]:
        article["paragraphs"][0]["qas"][0]["answers"] = [{"answer_start": 0, "text": "wrong"}]
    source.write_text(json.dumps(data))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="matching answer"):
        _import_squad(
            source,
            output,
            expected_sha256=digest,
            articles=2,
            paragraphs_per_article=1,
            questions_per_paragraph=1,
        )
    assert not output.exists()


def test_no_overwrite_or_unpinned_cli_import(tmp_path):
    source = tmp_path / "source.json"
    digest = _dataset(source)
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("retained")
    with pytest.raises(ValueError, match="empty directory"):
        _import_squad(source, output, expected_sha256=digest)
    assert marker.read_text() == "retained"
    with pytest.raises(SystemExit) as exc:
        main(["--input", str(source), "--output", str(tmp_path / "cli")])
    assert exc.value.code == 2
    assert not (tmp_path / "cli").exists()


def test_committed_external_corpus_preserves_size_license_and_attribution():
    root = Path(__file__).resolve().parents[1] / "benchmarks/retrieval/corpus_squad_v1"
    corpus = load_corpus(root)
    assert len(corpus.documents) == 32
    assert len(corpus.queries) == 96
    assert corpus.license == "CC-BY-SA-4.0"
    assert len(corpus.provenance["selected_articles"]) == 16
    assert {
        split: sum(query.split == split for query in corpus.queries) for split in ("dev", "test")
    } == {"dev": 48, "test": 48}
    manifest = json.loads((root / "manifest.json").read_text())
    assert all(
        doc["source"].startswith("https://en.wikipedia.org/wiki/") and doc["attribution"]
        for doc in manifest["documents"]
    )


@pytest.mark.parametrize("duplicate", ["context", "question"])
def test_normalized_duplicates_cannot_cross_splits(tmp_path, duplicate):
    source = tmp_path / "source.json"
    _dataset(source)
    data = json.loads(source.read_text())
    data["data"] = data["data"][:2]
    for index, article in enumerate(data["data"]):
        paragraph = article["paragraphs"][0]
        if duplicate == "context":
            paragraph["context"] = "Café ve çay." if index == 0 else "Cafe\u0301  ve çay."
        else:
            paragraph["qas"][0]["question"] = "Which drink?" if index == 0 else "WHICH  drink?"
        paragraph["qas"][0]["answers"] = [
            {"answer_start": paragraph["context"].index("çay"), "text": "çay"}
        ]
    source.write_text(json.dumps(data))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="too few eligible"):
        _import_squad(
            source,
            output,
            expected_sha256=digest,
            articles=2,
            paragraphs_per_article=1,
            questions_per_paragraph=1,
        )
    assert not output.exists()
