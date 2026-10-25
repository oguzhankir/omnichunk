"""Validated, source-addressable fixtures for retrieval experiments.

The on-disk manifest is deliberately independent of any chunker's output.
Evidence identifies canonical UTF-8 source bytes, never generated chunk IDs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnichunk.retrieval_eval import EvidenceSpan


@dataclass(frozen=True)
class Document:
    source_id: str
    path: str
    text: str
    language: str
    category: str
    split: str


@dataclass(frozen=True)
class Query:
    query_id: str
    text: str
    split: str
    evidence: tuple[EvidenceSpan, ...]


@dataclass(frozen=True)
class Corpus:
    corpus_id: str
    documents: tuple[Document, ...]
    queries: tuple[Query, ...]
    manifest_hash: str
    license: str = "MIT"
    provenance: dict[str, Any] | None = None
    source: str | None = None


def _text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{key} must contain valid Unicode text") from exc
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite manifest JSON value: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Manifest JSON numbers must be finite")
    return number


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _records(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key)
    if not isinstance(value, list) or not value or any(not isinstance(x, dict) for x in value):
        raise ValueError(f"{key} must contain nonempty object records")
    return value


def _split(record: dict[str, Any]) -> str:
    split = _text(record, "split")
    if split not in {"dev", "test"}:
        raise ValueError("split must be dev or test")
    return split


def load_corpus(path: Path) -> Corpus:
    """Load a manifest or corpus directory, rejecting corruption and split leakage.

    Hashes cover exact on-disk source bytes. Quotes must decode from nonempty,
    half-open UTF-8 ranges. A source and all its evidence belong to one split;
    Unicode/whitespace-equivalent documents and case-insensitive equivalent
    query texts cannot straddle dev and test. Sources retain their exact bytes.
    The license identifies the imported corpus; it does not relicense its data.
    """
    manifest_path = path / "manifest.json" if path.is_dir() else path
    manifest_raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(
            manifest_raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid corpus manifest JSON") from exc
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
    ):
        raise ValueError("Unsupported corpus schema_version")
    corpus_id = _text(manifest, "corpus_id")
    license_id = _text(manifest, "license")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", license_id):
        raise ValueError("license must be one SPDX-style license identifier")
    provenance = manifest.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError("provenance must be a JSON object")
    source = _text(manifest, "source") if "source" in manifest else None
    root = manifest_path.resolve().parent
    documents: list[Document] = []
    by_id: dict[str, Document] = {}
    content_splits: dict[str, str] = {}
    normalized_splits: dict[str, str] = {}
    source_paths: set[str] = set()
    for item in _records(manifest, "documents"):
        source_id, relative = _text(item, "source_id"), _text(item, "path")
        if source_id in by_id:
            raise ValueError(f"Duplicate source_id: {source_id}")
        source_path = (root / relative).resolve()
        if (
            Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or root not in source_path.parents
        ):
            raise ValueError(f"Document path escapes corpus root: {relative}")
        if str(source_path) in source_paths:
            raise ValueError(f"Duplicate source path: {relative}")
        if not source_path.is_file():
            raise ValueError(f"Document is not a regular file: {relative}")
        raw = source_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != _text(item, "sha256"):
            raise ValueError(f"Document checksum mismatch: {relative}")
        split = _split(item)
        if digest in content_splits and content_splits[digest] != split:
            raise ValueError("Identical document content leaks between splits")
        content_splits[digest] = split
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Document is not UTF-8: {relative}") from exc
        normalized_digest = hashlib.sha256(_normalized(text).encode("utf-8")).hexdigest()
        if normalized_digest in normalized_splits and normalized_splits[normalized_digest] != split:
            raise ValueError("Equivalent document content leaks between splits")
        normalized_splits[normalized_digest] = split
        document = Document(
            source_id, relative, text, _text(item, "language"), _text(item, "category"), split
        )
        documents.append(document)
        by_id[source_id] = document
        source_paths.add(str(source_path))
    queries: list[Query] = []
    query_ids: set[str] = set()
    question_splits: dict[str, str] = {}
    labeled_sources: set[str] = set()
    for item in _records(manifest, "queries"):
        query_id, question = _text(item, "query_id"), _text(item, "text")
        if query_id in query_ids:
            raise ValueError(f"Duplicate query_id: {query_id}")
        split = _split(item)
        normalized = _normalized(question.casefold())
        if normalized in question_splits and question_splits[normalized] != split:
            raise ValueError("Identical query text leaks between splits")
        question_splits[normalized] = split
        spans: list[EvidenceSpan] = []
        for evidence in _records(item, "evidence"):
            source_id = _text(evidence, "source_id")
            if source_id not in by_id:
                raise ValueError(f"Unknown evidence source_id: {source_id}")
            document = by_id[source_id]
            if document.split != split:
                raise ValueError("Evidence source belongs to another split")
            start, end = evidence.get("start"), evidence.get("end")
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end <= start
                or end > len(document.text.encode("utf-8"))
            ):
                raise ValueError("Evidence range must identify nonempty source bytes")
            try:
                quote = document.text.encode("utf-8")[start:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Evidence range cuts a UTF-8 character") from exc
            if quote != _text(evidence, "quote"):
                raise ValueError("Evidence quote does not match source bytes")
            spans.append(EvidenceSpan(source_id, start, end))
            labeled_sources.add(source_id)
        queries.append(Query(query_id, question, split, tuple(spans)))
        query_ids.add(query_id)
    if labeled_sources != set(by_id):
        raise ValueError("Every document must have evidence labels")
    return Corpus(
        corpus_id,
        tuple(documents),
        tuple(queries),
        hashlib.sha256(manifest_raw).hexdigest(),
        license_id,
        provenance,
        source,
    )
