"""Boundary validation and repeatable native identifiers for index exports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from omnichunk import Chunker, stable_chunk_id, weaviate_object_id
from omnichunk import serialization as serializers
from omnichunk.store import ChunkStore
from omnichunk.store.chunk_store import LegacyStoreError
from omnichunk.types import ByteRange

EXPORTERS = [
    serializers.chunks_to_pinecone_vectors,
    serializers.chunks_to_weaviate_objects,
    serializers.chunks_to_supabase_rows,
]


@pytest.mark.parametrize("exporter", EXPORTERS)
@pytest.mark.parametrize(
    "vectors, message",
    [
        ([[], []], "positive dimension"),
        ([[1.0], [1.0, 2.0]], "dimension"),
        ([[float("nan")], [1.0]], "finite real numbers"),
        ([[1.0], [float("inf")]], "finite real numbers"),
        ([[float("-inf")], [1.0]], "finite real numbers"),
        ([[True], [1.0]], "finite real numbers"),
        ([["1.0"], [1.0]], "finite real numbers"),
        ([[[1.0]], [1.0]], "finite real numbers"),
        ([[10**400], [1.0]], "finite real numbers"),
    ],
)
def test_vector_exports_reject_invalid_provider_payload(exporter, vectors, message):
    chunker = Chunker(context_mode="none")
    chunks = chunker.chunk("a.txt", "one") + chunker.chunk("b.txt", "two")
    with pytest.raises(ValueError, match=message):
        exporter(chunks, vectors)


@pytest.mark.parametrize("exporter", EXPORTERS)
def test_vector_exports_accept_empty_batch_and_json_numeric_vectors(exporter):
    assert exporter([], []) == []
    chunks = Chunker().chunk("a.txt", "one")
    rows = exporter(chunks, [[1, 0, -1]])
    assert json.loads(json.dumps(rows, allow_nan=False)) == rows


def test_weaviate_native_id_survives_retries_and_source_moves():
    chunk = Chunker(context_mode="none").chunk("a.txt", "one")[0]
    moved = replace(chunk, byte_range=ByteRange(10, 13), index=8)
    first = serializers.chunks_to_weaviate_objects([chunk], [[1.0]])[0]
    retry = serializers.chunks_to_weaviate_objects([moved], [[2.0]])[0]
    assert UUID(first["id"]).version == 5
    assert first["id"] == retry["id"] == weaviate_object_id(stable_chunk_id(chunk))
    assert first["properties"]["chunk_id"] == stable_chunk_id(chunk)
    other = Chunker(context_mode="none").chunk("b.txt", "one")[0]
    assert first["id"] != serializers.chunks_to_weaviate_objects([other], [[1.0]])[0]["id"]


def test_framework_exports_set_native_document_ids(monkeypatch):
    class Document:
        def __init__(self, **kwargs):
            self.values = kwargs

    monkeypatch.setattr(
        serializers.importlib, "import_module", lambda _name: SimpleNamespace(Document=Document)
    )
    chunks = Chunker().chunk("a.txt", "one")
    chunk_id = stable_chunk_id(chunks[0])
    langchain = serializers.chunks_to_langchain_docs(chunks)[0]
    llamaindex = serializers.chunks_to_llamaindex_docs(chunks)[0]
    assert langchain.values["id"] == chunk_id
    assert llamaindex.values["id_"] == chunk_id
    assert langchain.values["metadata"]["chunk_id"] == chunk_id
    assert llamaindex.values["metadata"]["chunk_id"] == chunk_id


@pytest.mark.parametrize("adapter", ["pinecone", "weaviate", "supabase"])
def test_stream_upsert_rejects_cross_batch_dimension_drift(tmp_path, adapter):
    path = tmp_path / "source.txt"
    path.write_text("alpha beta gamma delta " * 5)
    calls = 0

    def embed(texts):
        nonlocal calls
        calls += 1
        return [[1.0] * calls for _ in texts]

    chunker = Chunker(max_chunk_size=20, size_unit="chars", context_mode="none")
    batches = chunker.stream_upsert(str(path), embed_fn=embed, adapter=adapter, batch_size=1)
    assert len(next(batches).rows) == 1
    with pytest.raises(ValueError, match="dimension 2; expected 1 across all batches"):
        next(batches)


@pytest.mark.parametrize("version", [1, 999])
def test_store_rejects_versioned_empty_database_without_modifying_it(tmp_path: Path, version: int):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
    original = path.read_bytes()
    with pytest.raises(LegacyStoreError, match=f"Unsupported store schema {version}"):
        ChunkStore(path)
    assert path.read_bytes() == original
