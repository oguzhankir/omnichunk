"""Corpus labels must survive Unicode slicing and never leak across splits."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.retrieval.corpus import load_corpus

CORPUS = Path(__file__).resolve().parents[1] / "benchmarks/retrieval/corpus_v1"


def _manifest(tmp_path: Path) -> tuple[Path, dict]:
    text = "# Policy\n資料 café 🙂: keep the old source snapshot.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    quote = "資料 café 🙂: keep the old source snapshot."
    start = text.encode().index(quote.encode())
    manifest = {
        "schema_version": 1,
        "corpus_id": "test",
        "license": "MIT",
        "documents": [
            {
                "source_id": "source",
                "path": "source.md",
                "language": "en",
                "category": "markdown",
                "split": "dev",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
        "queries": [
            {
                "query_id": "query",
                "text": "Which source snapshot should be kept?",
                "split": "dev",
                "evidence": [
                    {
                        "source_id": "source",
                        "start": start,
                        "end": start + len(quote.encode()),
                        "quote": quote,
                    }
                ],
            }
        ],
    }
    return tmp_path / "manifest.json", manifest


def _write(path: Path, manifest: dict) -> Path:
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_frozen_starter_corpus_is_balanced_and_all_evidence_is_valid() -> None:
    corpus = load_corpus(CORPUS)
    assert len(corpus.documents) == 30 and len(corpus.queries) == 300
    assert Counter(d.language for d in corpus.documents) == {"en": 10, "tr": 10, "ja": 10}
    assert Counter(d.category for d in corpus.documents) == {"code": 12, "markdown": 9, "table": 9}
    assert Counter(q.split for q in corpus.queries) == {"dev": 180, "test": 120}
    assert len(corpus.manifest_hash) == 64
    assert corpus == load_corpus(CORPUS / "manifest.json")
    # These are substantive source units rather than a question/answer-per-file corpus.
    assert min(len(d.text.encode()) for d in corpus.documents) >= 1_000
    assert len({d.text for d in corpus.documents}) == 30


def test_manifest_hash_tracks_labels_and_ranges_are_utf8_bytes(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    corpus = load_corpus(_write(path, manifest))
    span = corpus.queries[0].evidence[0]
    quote = manifest["queries"][0]["evidence"][0]["quote"]
    assert corpus.documents[0].text.encode()[span.start : span.end].decode() == quote
    manifest["queries"][0]["text"] += " Please explain."
    assert load_corpus(_write(path, manifest)).manifest_hash != corpus.manifest_hash


@pytest.mark.parametrize("schema", [0, 2, True, None, "1"])
def test_unknown_schema_rejected(tmp_path: Path, schema) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["schema_version"] = schema
    with pytest.raises(ValueError, match="schema_version"):
        load_corpus(_write(path, manifest))


def test_corrupt_json_and_source_hash_are_rejected(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        load_corpus(path)
    _write(path, manifest)
    (tmp_path / "source.md").write_text("edited", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_corpus(path)


@pytest.mark.parametrize("relative", ["../source.md", "/tmp/source.md", "inner/../source.md"])
def test_document_paths_cannot_traverse(tmp_path: Path, relative: str) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["documents"][0]["path"] = relative
    with pytest.raises(ValueError, match="escapes"):
        load_corpus(_write(path, manifest))


def test_document_symlink_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    path, manifest = _manifest(root)
    outside = tmp_path / "outside.md"
    outside.write_bytes((root / "source.md").read_bytes())
    try:
        (root / "link.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    manifest["documents"][0]["path"] = "link.md"
    with pytest.raises(ValueError, match="escapes"):
        load_corpus(_write(path, manifest))


@pytest.mark.parametrize(
    "key, message", [("source_id", "Duplicate source_id"), ("path", "Duplicate source path")]
)
def test_duplicate_sources_rejected(tmp_path: Path, key: str, message: str) -> None:
    path, manifest = _manifest(tmp_path)
    second = dict(manifest["documents"][0])
    if key == "path":
        second["source_id"] = "other"
    manifest["documents"].append(second)
    with pytest.raises(ValueError, match=message):
        load_corpus(_write(path, manifest))


def test_duplicate_queries_and_cross_split_queries_rejected(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["queries"].append(dict(manifest["queries"][0]))
    with pytest.raises(ValueError, match="Duplicate query_id"):
        load_corpus(_write(path, manifest))
    manifest["queries"][1].update(query_id="other", split="test")
    with pytest.raises(ValueError, match="query text leaks"):
        load_corpus(_write(path, manifest))


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("start", True, "range"),
        ("end", 99999, "range"),
        ("start", 10, "UTF-8"),
        ("quote", "incorrect", "quote"),
        ("source_id", "unknown", "Unknown"),
    ],
)
def test_invalid_evidence_rejected(tmp_path: Path, field: str, value, message: str) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["queries"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError, match=message):
        load_corpus(_write(path, manifest))


def test_evidence_cannot_cross_split(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["queries"][0]["split"] = "test"
    with pytest.raises(ValueError, match="another split"):
        load_corpus(_write(path, manifest))


def test_identical_sources_cannot_cross_split(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    (tmp_path / "duplicate.md").write_bytes((tmp_path / "source.md").read_bytes())
    second = dict(manifest["documents"][0], source_id="other", path="duplicate.md", split="test")
    manifest["documents"].append(second)
    with pytest.raises(ValueError, match="content leaks"):
        load_corpus(_write(path, manifest))


@pytest.mark.parametrize("field", ["language", "category", "split"])
def test_document_labels_required(tmp_path: Path, field: str) -> None:
    path, manifest = _manifest(tmp_path)
    del manifest["documents"][0][field]
    with pytest.raises(ValueError, match=field):
        load_corpus(_write(path, manifest))


def test_unlabeled_document_rejected(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    source = tmp_path / "other.md"
    source.write_text("other source", encoding="utf-8")
    second = dict(
        manifest["documents"][0],
        source_id="other",
        path="other.md",
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest["documents"].append(second)
    with pytest.raises(ValueError, match="Every document"):
        load_corpus(_write(path, manifest))


def test_external_corpus_retains_original_license_and_provenance(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    manifest.update(
        license="CC-BY-SA-4.0",
        source="https://example.org/original-dataset",
        provenance={"revision": "frozen-revision", "sha256": "original-download-hash"},
    )
    corpus = load_corpus(_write(path, manifest))
    assert corpus.license == "CC-BY-SA-4.0"
    assert corpus.source == manifest["source"]
    assert corpus.provenance == manifest["provenance"]
    assert (
        corpus.documents[0]
        .text.encode()[corpus.queries[0].evidence[0].start : corpus.queries[0].evidence[0].end]
        .decode()
        == manifest["queries"][0]["evidence"][0]["quote"]
    )


@pytest.mark.parametrize(
    "extra",
    [
        '"schema_version": 2',
        '"provenance": {"revision": "first", "revision": "second"}',
        '"provenance": {"score": NaN}',
        '"provenance": {"score": Infinity}',
        '"provenance": {"score": 1e999}',
    ],
)
def test_ambiguous_or_nonfinite_manifest_json_is_rejected(tmp_path: Path, extra: str) -> None:
    path, manifest = _manifest(tmp_path)
    encoded = json.dumps(manifest)
    path.write_text(encoded[:-1] + "," + extra + "}", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest JSON"):
        load_corpus(path)


@pytest.mark.parametrize("license_id", ["", " ", "MIT OR Apache-2.0", None, 42])
def test_license_requires_one_explicit_identifier(tmp_path: Path, license_id) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["license"] = license_id
    with pytest.raises(ValueError, match="license"):
        load_corpus(_write(path, manifest))


@pytest.mark.parametrize("change", ["line_endings", "unicode", "whitespace"])
def test_equivalent_document_bytes_cannot_cross_splits(tmp_path: Path, change: str) -> None:
    path, manifest = _manifest(tmp_path)
    text = (tmp_path / "source.md").read_text(encoding="utf-8")
    if change == "line_endings":
        text = text.replace("\n", "\r\n")
    elif change == "unicode":
        text = unicodedata.normalize("NFD", text)
    else:
        text = text.replace(" ", "  ")
    raw = text.encode("utf-8")
    (tmp_path / "equivalent.md").write_bytes(raw)
    manifest["documents"].append(
        dict(
            manifest["documents"][0],
            source_id="equivalent",
            path="equivalent.md",
            sha256=hashlib.sha256(raw).hexdigest(),
            split="test",
        )
    )
    with pytest.raises(ValueError, match="content leaks"):
        load_corpus(_write(path, manifest))


def test_unicode_equivalent_query_text_cannot_cross_splits(tmp_path: Path) -> None:
    path, manifest = _manifest(tmp_path)
    manifest["queries"][0]["text"] = "Which café?"
    manifest["queries"].append(
        dict(
            manifest["queries"][0],
            query_id="equivalent",
            text="  WHICH CAFE\u0301?  ",
            split="test",
        )
    )
    with pytest.raises(ValueError, match="query text leaks"):
        load_corpus(_write(path, manifest))
