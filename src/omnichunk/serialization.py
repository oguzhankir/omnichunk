from __future__ import annotations

import csv
import hashlib
import importlib
import json
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any

from omnichunk.types import Chunk


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Convert a Chunk dataclass into a serializable dictionary."""
    value = _to_serializable(chunk)
    if not isinstance(value, dict):
        return {}
    return value


def chunks_to_jsonl(chunks: Sequence[Chunk], *, output_path: str | None = None) -> str:
    """Serialize chunks into JSONL. Optionally write output to a file path."""
    lines = [
        json.dumps(chunk_to_dict(chunk), ensure_ascii=False, sort_keys=True)
        for chunk in chunks
    ]
    payload = "\n".join(lines)
    if lines:
        payload += "\n"

    if output_path:
        Path(output_path).write_text(payload, encoding="utf-8")

    return payload


def chunks_to_csv(chunks: Sequence[Chunk], *, output_path: str | None = None) -> str:
    """Serialize chunks into CSV with flattened context fields."""
    columns = [
        "filepath",
        "language",
        "content_type",
        "index",
        "total_chunks",
        "byte_start",
        "byte_end",
        "line_start",
        "line_end",
        "token_count",
        "char_count",
        "nws_count",
        "breadcrumb",
        "section_type",
        "entity_count",
        "text",
        "contextualized_text",
    ]

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()

    for chunk in chunks:
        writer.writerow(
            {
                "filepath": chunk.context.filepath,
                "language": chunk.context.language,
                "content_type": chunk.context.content_type.value,
                "index": chunk.index,
                "total_chunks": chunk.total_chunks,
                "byte_start": chunk.byte_range.start,
                "byte_end": chunk.byte_range.end,
                "line_start": chunk.line_range.start,
                "line_end": chunk.line_range.end,
                "token_count": chunk.token_count,
                "char_count": chunk.char_count,
                "nws_count": chunk.nws_count,
                "breadcrumb": " > ".join(chunk.context.breadcrumb),
                "section_type": chunk.context.section_type,
                "entity_count": len(chunk.context.entities),
                "text": chunk.text,
                "contextualized_text": chunk.contextualized_text,
            }
        )

    payload = buffer.getvalue()

    if output_path:
        Path(output_path).write_text(payload, encoding="utf-8")

    return payload


def chunks_to_langchain_docs(
    chunks: Sequence[Chunk],
    *,
    use_contextualized_text: bool = True,
) -> list[Any]:
    """Convert chunks to LangChain Document objects."""
    document_cls = _import_langchain_document_class()
    docs: list[Any] = []

    for chunk in chunks:
        content = chunk.contextualized_text if use_contextualized_text else chunk.text
        docs.append(
            document_cls(
                page_content=content,
                metadata=_chunk_metadata(chunk),
            )
        )

    return docs


def chunks_to_pinecone_vectors(
    chunks: Sequence[Chunk],
    embeddings: Sequence[list[float]],
    *,
    namespace: str = "",
    use_contextualized_text: bool = True,
) -> list[dict[str, Any]]:
    """Convert chunks to Pinecone upsert-ready dicts (no Pinecone client required).

    Each dict has ``id``, ``values``, ``metadata``. If ``namespace`` is non-empty, a
    top-level ``namespace`` key is set on each dict.
    """
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"embeddings length ({len(embeddings)}) must match chunks length ({len(chunks)})"
        )

    out: list[dict[str, Any]] = []
    for chunk, values in zip(chunks, embeddings):
        row: dict[str, Any] = {
            "id": _stable_vector_id(chunk),
            "values": list(values),
            "metadata": _vectordb_metadata(chunk, use_contextualized_text=use_contextualized_text),
        }
        if namespace:
            row["namespace"] = namespace
        out.append(row)
    return out


def chunks_to_weaviate_objects(
    chunks: Sequence[Chunk],
    embeddings: Sequence[list[float]],
    *,
    class_name: str = "OmnichunkDocument",
    use_contextualized_text: bool = True,
) -> list[dict[str, Any]]:
    """Convert chunks to Weaviate batch-import-ready dicts (no Weaviate client required)."""
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"embeddings length ({len(embeddings)}) must match chunks length ({len(chunks)})"
        )

    return [
        {
            "class": class_name,
            "vector": list(values),
            "properties": _vectordb_metadata(
                chunk,
                use_contextualized_text=use_contextualized_text,
            ),
        }
        for chunk, values in zip(chunks, embeddings)
    ]


def chunks_to_supabase_rows(
    chunks: Sequence[Chunk],
    embeddings: Sequence[list[float]],
    *,
    use_contextualized_text: bool = True,
) -> list[dict[str, Any]]:
    """Convert chunks to Supabase / pgvector INSERT-ready dicts (no client required)."""
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"embeddings length ({len(embeddings)}) must match chunks length ({len(chunks)})"
        )

    rows: list[dict[str, Any]] = []
    for chunk, values in zip(chunks, embeddings):
        meta = _vectordb_metadata(chunk, use_contextualized_text=use_contextualized_text)
        content = meta.pop("text")
        rows.append(
            {
                "content": content,
                "embedding": list(values),
                **meta,
            }
        )
    return rows


def chunks_to_llamaindex_docs(
    chunks: Sequence[Chunk],
    *,
    use_contextualized_text: bool = True,
) -> list[Any]:
    """Convert chunks to LlamaIndex Document objects."""
    document_cls = _import_llamaindex_document_class()
    docs: list[Any] = []

    for chunk in chunks:
        content = chunk.contextualized_text if use_contextualized_text else chunk.text
        docs.append(document_cls(text=content, metadata=_chunk_metadata(chunk)))

    return docs


def stable_chunk_id(chunk: Chunk, filepath: str | None = None) -> str:
    """Return a stable SHA-256 hex ID for a chunk (same as Pinecone/Weaviate export IDs).

    Uses filepath (from ``chunk.context`` or override), chunk index, and byte range.
    Identical to :func:`chunks_to_pinecone_vectors` row ``id`` values.
    """
    fp = filepath if filepath is not None else chunk.context.filepath
    raw = f"{fp}\0{chunk.index}\0{chunk.byte_range.start}\0{chunk.byte_range.end}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_vector_id(chunk: Chunk) -> str:
    return stable_chunk_id(chunk)


def _vectordb_metadata(chunk: Chunk, *, use_contextualized_text: bool) -> dict[str, Any]:
    text = chunk.contextualized_text if use_contextualized_text else chunk.text
    return {
        "text": text,
        "filepath": chunk.context.filepath,
        "language": chunk.context.language,
        "content_type": chunk.context.content_type.value,
        "index": chunk.index,
        "total_chunks": chunk.total_chunks,
        "byte_start": chunk.byte_range.start,
        "byte_end": chunk.byte_range.end,
        "line_start": chunk.line_range.start,
        "line_end": chunk.line_range.end,
        "token_count": chunk.token_count,
        "char_count": chunk.char_count,
        "nws_count": chunk.nws_count,
        "breadcrumb": " > ".join(chunk.context.breadcrumb),
    }


def _chunk_metadata(chunk: Chunk) -> dict[str, Any]:
    return {
        "filepath": chunk.context.filepath,
        "language": chunk.context.language,
        "content_type": chunk.context.content_type.value,
        "index": chunk.index,
        "total_chunks": chunk.total_chunks,
        "byte_start": chunk.byte_range.start,
        "byte_end": chunk.byte_range.end,
        "line_start": chunk.line_range.start,
        "line_end": chunk.line_range.end,
        "token_count": chunk.token_count,
        "char_count": chunk.char_count,
        "nws_count": chunk.nws_count,
        "breadcrumb": list(chunk.context.breadcrumb),
        "section_type": chunk.context.section_type,
        "heading_hierarchy": list(chunk.context.heading_hierarchy),
    }


def _import_langchain_document_class() -> Any:
    try:
        documents_module = importlib.import_module("langchain_core.documents")
        document_cls = getattr(documents_module, "Document", None)
        if document_cls is None:
            raise AttributeError("Document type not found in langchain_core.documents")
        return document_cls
    except Exception:
        pass

    try:
        schema_module = importlib.import_module("langchain.schema")
        document_cls = getattr(schema_module, "Document", None)
        if document_cls is None:
            raise AttributeError("Document type not found in langchain.schema")
        return document_cls
    except Exception as exc:
        raise ImportError(
            "LangChain support requires 'langchain-core' or 'langchain' to be installed."
        ) from exc


def _import_llamaindex_document_class() -> Any:
    try:
        schema_module = importlib.import_module("llama_index.core.schema")
        document_cls = getattr(schema_module, "Document", None)
        if document_cls is None:
            raise AttributeError("Document type not found in llama_index.core.schema")
        return document_cls
    except Exception as exc:
        raise ImportError(
            "LlamaIndex support requires 'llama-index-core' (or 'llama-index') to be installed."
        ) from exc


def _to_serializable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value

    if is_dataclass(value):
        return {
            field.name: _to_serializable(getattr(value, field.name))
            for field in fields(value)
        }

    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_to_serializable(item) for item in value]

    if isinstance(value, tuple):
        return [_to_serializable(item) for item in value]

    return value
