from __future__ import annotations

import json
from dataclasses import replace

import pytest

from omnichunk import Chunker
from omnichunk.serialization import (
    chunk_to_dict,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
    chunks_to_pinecone_upsert_request,
    chunks_to_pinecone_vectors,
)


def annotated_chunk():
    chunk = Chunker(context_mode="none").chunk("policy.txt", "The policy is current.")[0]
    return replace(chunk, metadata={"acl": ["staff"], "page": {"number": 2, "language": "日本語"}})


def test_pinecone_request_namespace_and_complete_metadata():
    chunk = annotated_chunk()
    request = chunks_to_pinecone_upsert_request(
        [chunk], [[0.1, 0.2]], namespace="tenant-a", filter_metadata=[{"acl": ["staff"], "page": 2}]
    )
    assert set(request) == {"namespace", "vectors"}
    assert request["namespace"] == "tenant-a"
    row = request["vectors"][0]
    assert set(row) == {"id", "values", "metadata"}
    assert row["id"] == chunks_to_pinecone_vectors([chunk], [[0.1, 0.2]])[0]["id"]
    assert row["metadata"]["acl"] == ["staff"]
    assert json.loads(row["metadata"]["omnichunk"]) == chunk_to_dict(chunk)


@pytest.mark.parametrize(
    "metadata",
    [
        {"text": "spoofed"},
        {"omnichunk": "spoofed"},
        {"nested": {"a": 1}},
        {"null": None},
        {"bad": float("nan")},
        {1: "key"},
        {"$reserved": "bad"},
        {"numeric_id": 2**53 + 1},
        {"numeric_id": 10**400},
        ["not-an-object"],
    ],
)
def test_pinecone_request_rejects_invalid_filter_metadata(metadata):
    with pytest.raises(ValueError):
        chunks_to_pinecone_upsert_request([annotated_chunk()], [[1.0]], filter_metadata=[metadata])


def test_pinecone_rejects_oversized_metadata_without_truncating():
    chunk = replace(annotated_chunk(), metadata={"large": "界" * 20000})
    with pytest.raises(ValueError, match="exceeds"):
        chunks_to_pinecone_upsert_request([chunk], [[1.0]])


@pytest.mark.parametrize("limit", [0, 40961, True])
def test_pinecone_metadata_limit_validation(limit):
    with pytest.raises(ValueError, match="max_metadata_bytes"):
        chunks_to_pinecone_upsert_request([annotated_chunk()], [[1.0]], max_metadata_bytes=limit)


def test_pinecone_metadata_count_must_match_chunks():
    with pytest.raises(ValueError, match="length"):
        chunks_to_pinecone_upsert_request([annotated_chunk()], [[1.0]], filter_metadata=[])


@pytest.mark.parametrize("value", [1e300, -1e300])
def test_pinecone_request_rejects_float32_vector_overflow(value):
    with pytest.raises(ValueError, match="float32"):
        chunks_to_pinecone_upsert_request([annotated_chunk()], [[value]])


def test_pinecone_filter_identifiers_preserve_exact_values():
    request = chunks_to_pinecone_upsert_request(
        [annotated_chunk()],
        [[3.4028234663852886e38]],
        filter_metadata=[{"exact_integer": 2**60, "string_id": str(2**53 + 1)}],
    )
    metadata = request["vectors"][0]["metadata"]
    assert metadata["exact_integer"] == 2**60
    assert metadata["string_id"] == str(2**53 + 1)


@pytest.mark.parametrize(
    "adapter,module",
    [(chunks_to_langchain_docs, "langchain_core"), (chunks_to_llamaindex_docs, "llama_index.core")],
)
def test_framework_conversion_keeps_complete_chunk_metadata(adapter, module):
    pytest.importorskip(module)
    chunk = annotated_chunk()
    document = adapter([chunk])[0]
    assert document.metadata["omnichunk"] == chunk_to_dict(chunk)
    document.metadata["omnichunk"]["metadata"]["acl"].append("other")
    assert chunk.metadata["acl"] == ["staff"]


def test_framework_conversion_rejects_non_json_metadata():
    pytest.importorskip("langchain_core")
    chunk = replace(annotated_chunk(), metadata={"bad": object()})
    with pytest.raises(ValueError, match="finite JSON"):
        chunks_to_langchain_docs([chunk])


def test_llamaindex_full_snapshot_does_not_duplicate_text_in_model_content():
    schema = pytest.importorskip("llama_index.core.schema")
    chunk = annotated_chunk()
    document = chunks_to_llamaindex_docs([chunk])[0]
    assert document.get_content(metadata_mode=schema.MetadataMode.EMBED).count(chunk.text) == 1
    assert document.get_content(metadata_mode=schema.MetadataMode.LLM).count(chunk.text) == 1
    assert document.metadata["omnichunk"]["text"] == chunk.text
