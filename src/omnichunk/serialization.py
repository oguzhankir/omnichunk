from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from io import StringIO
from numbers import Real
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ContentType,
    EntityInfo,
    EntityType,
    ImportInfo,
    Language,
    LineRange,
    SiblingInfo,
    SourceDescriptor,
)

CHUNK_SCHEMA_VERSION = 2


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Convert every chunk field to the versioned JSON representation.

    Unversioned v1 dictionaries remain readable with :func:`chunk_from_dict`.
    Unknown schema versions are rejected rather than silently losing fields.
    """
    value = _to_serializable(chunk)
    if not isinstance(value, dict):
        return {}
    return {"schema_version": CHUNK_SCHEMA_VERSION, **value}


def _entity_info_from_dict(d: dict[str, Any]) -> EntityInfo:
    br = d.get("byte_range") or {}
    lr = d.get("line_range") or {}
    try:
        etype = EntityType(str(d.get("type", "function")))
    except ValueError:
        etype = EntityType.FUNCTION
    return EntityInfo(
        name=str(d.get("name", "")),
        type=etype,
        signature=str(d.get("signature", "")),
        docstring=d.get("docstring"),
        byte_range=ByteRange(int(br["start"]), int(br["end"])) if br else None,
        line_range=LineRange(int(lr["start"]), int(lr["end"])) if lr else None,
        is_partial=bool(d.get("is_partial", False)),
        parent=d.get("parent"),
    )


def chunk_from_dict(data: dict[str, Any]) -> Chunk:
    """Read v2 or legacy v1/unversioned chunks, including all context fields."""
    schema = data.get("schema_version", 1)
    if type(schema) is not int or schema not in (1, CHUNK_SCHEMA_VERSION):
        raise ValueError(f"Unsupported chunk schema version: {schema!r}")
    ctx_raw = data.get("context") or {}
    ct_raw = ctx_raw.get("content_type", "prose")
    if isinstance(ct_raw, str):
        try:
            content_type = ContentType(ct_raw)
        except ValueError:
            content_type = ContentType.PROSE
    else:
        content_type = ContentType.PROSE

    entities = [
        _entity_info_from_dict(e) for e in ctx_raw.get("entities") or [] if isinstance(e, dict)
    ]
    scope = [_entity_info_from_dict(e) for e in ctx_raw.get("scope") or []]
    siblings = [
        SiblingInfo(
            name=str(s["name"]),
            type=EntityType(s["type"]),
            position=s["position"],
            distance=int(s["distance"]),
            signature=str(s.get("signature", "")),
        )
        for s in ctx_raw.get("siblings") or []
    ]
    imports = [ImportInfo(**i) for i in ctx_raw.get("imports") or []]
    source_raw = data.get("source")
    source = SourceDescriptor(**source_raw) if source_raw is not None else None

    br = data.get("byte_range") or {}
    lr = data.get("line_range") or {}
    return Chunk(
        text=str(data.get("text", "")),
        contextualized_text=str(data.get("contextualized_text", data.get("text", ""))),
        byte_range=ByteRange(start=int(br.get("start", 0)), end=int(br.get("end", 0))),
        line_range=LineRange(start=int(lr.get("start", 0)), end=int(lr.get("end", 0))),
        index=int(data.get("index", 0)),
        total_chunks=int(data.get("total_chunks", -1)),
        context=ChunkContext(
            filepath=str(ctx_raw.get("filepath", "")),
            language=cast(Language, ctx_raw.get("language", "plaintext")),
            content_type=content_type,
            scope=scope,
            breadcrumb=list(ctx_raw.get("breadcrumb") or []),
            entities=entities,
            siblings=siblings,
            imports=imports,
            heading_hierarchy=list(ctx_raw.get("heading_hierarchy") or []),
            section_type=str(ctx_raw.get("section_type", "")),
            parse_errors=list(ctx_raw.get("parse_errors") or []),
            format_metadata=dict(ctx_raw.get("format_metadata", {})),
        ),
        token_count=int(data.get("token_count", 0)),
        char_count=int(data.get("char_count", 0)),
        nws_count=int(data.get("nws_count", 0)),
        source=source,
        config_fingerprint=str(data.get("config_fingerprint", "")),
        occurrence=int(data.get("occurrence", 0)),
        metadata=dict(data.get("metadata") or {}),
    )


def chunks_to_jsonl(chunks: Sequence[Chunk], *, output_path: str | None = None) -> str:
    """Serialize chunks into JSONL. Optionally write output to a file path."""
    lines = [
        json.dumps(chunk_to_dict(chunk), ensure_ascii=False, sort_keys=True) for chunk in chunks
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
                id=stable_chunk_id(chunk),
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
    top-level ``namespace`` key is set on each dict for legacy compatibility.
    That legacy shape is not an SDK request. Prefer
    :func:`chunks_to_pinecone_upsert_request`, which places the namespace on the
    request envelope and preserves complete chunk metadata.
    """
    embeddings = _validated_vectors(chunks, embeddings)

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


def _strict_json_copy(value: Any) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("Metadata object keys must be strings")
        return {key: _strict_json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strict_json_copy(item) for item in value]
    raise ValueError("Metadata must contain finite JSON values")


def _chunk_snapshot(chunk: Chunk) -> dict[str, Any]:
    # Validate dictionaries before chunk_to_dict's legacy key normalization.
    for metadata in (
        chunk.metadata,
        chunk.context.format_metadata,
        chunk.source.metadata if chunk.source else {},
    ):
        _strict_json_copy(metadata)
    result: dict[str, Any] = _strict_json_copy(chunk_to_dict(chunk))
    return result


def chunks_to_pinecone_upsert_request(
    chunks: Sequence[Chunk],
    embeddings: Sequence[list[float]],
    *,
    namespace: str = "",
    use_contextualized_text: bool = True,
    filter_metadata: Sequence[Mapping[str, Any]] | None = None,
    max_metadata_bytes: int = 40 * 1024,
) -> dict[str, Any]:
    """Build ``index.upsert(**request)`` with namespace on the request envelope.

    Pinecone metadata permits flat scalars and string lists, so complete source,
    chunk and format metadata is preserved as JSON in ``metadata['omnichunk']``.
    Supply per-chunk ``filter_metadata`` for queryable ACL/page/source fields.
    Names colliding with generated fields, unsupported values and oversized
    metadata fail explicitly. No fields are silently dropped or truncated.
    Existing legacy vector IDs are retained; this is a request-shape migration.
    """
    if not isinstance(namespace, str):
        raise ValueError("namespace must be a string")
    if type(max_metadata_bytes) is not int or not 0 < max_metadata_bytes <= 40 * 1024:
        raise ValueError("max_metadata_bytes must be between 1 and 40960")
    if filter_metadata is not None and len(filter_metadata) != len(chunks):
        raise ValueError("filter_metadata length must match chunks length")
    vectors = chunks_to_pinecone_vectors(
        chunks, embeddings, use_contextualized_text=use_contextualized_text
    )
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        metadata = vector["metadata"]
        metadata["omnichunk"] = json.dumps(
            _chunk_snapshot(chunk),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if filter_metadata is not None:
            if not isinstance(filter_metadata[index], Mapping):
                raise ValueError("filter_metadata entries must be mappings")
            extra = _strict_json_copy(filter_metadata[index])
            for key, value in extra.items():
                if key.startswith("$"):
                    raise ValueError("Pinecone filter metadata keys cannot start with '$'")
                if key in metadata:
                    raise ValueError(f"filter_metadata collides with generated field {key!r}")
                if not (
                    type(value) in (str, bool, int, float)
                    or (isinstance(value, list) and all(type(item) is str for item in value))
                ):
                    raise ValueError("Pinecone filter metadata requires scalars or string lists")
                if type(value) is int:
                    try:
                        exact = math.isfinite(float(value)) and int(float(value)) == value
                    except OverflowError:
                        exact = False
                    if not exact:
                        raise ValueError(
                            "Pinecone integer filter metadata must be exactly representable "
                            "as float64; use strings for identifiers"
                        )
                metadata[key] = value
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > max_metadata_bytes:
            raise ValueError(f"Pinecone metadata exceeds {max_metadata_bytes} bytes")
    return {"namespace": namespace, "vectors": vectors}


def chunks_to_weaviate_objects(
    chunks: Sequence[Chunk],
    embeddings: Sequence[list[float]],
    *,
    class_name: str = "OmnichunkDocument",
    use_contextualized_text: bool = True,
) -> list[dict[str, Any]]:
    """Convert chunks to Weaviate REST batch objects with deterministic UUIDs.

    Retries address the same object. Convert removal IDs with
    :func:`weaviate_object_id` before deleting from Weaviate. For the Python v4
    client, pass ``id`` as ``uuid`` and ``properties``/``vector`` explicitly.
    Existing objects imported without IDs require a one-time rebuild.
    """
    embeddings = _validated_vectors(chunks, embeddings)

    return [
        {
            "class": class_name,
            "id": weaviate_object_id(stable_chunk_id(chunk)),
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
    embeddings = _validated_vectors(chunks, embeddings)

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
        docs.append(
            document_cls(
                id_=stable_chunk_id(chunk),
                text=content,
                metadata=_chunk_metadata(chunk),
                # The full provenance snapshot also contains raw/rendered text.
                # Keep it accessible without duplicating that text in prompts.
                excluded_embed_metadata_keys=["omnichunk"],
                excluded_llm_metadata_keys=["omnichunk"],
            )
        )

    return docs


def _validated_vectors(
    chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]
) -> list[list[float]]:
    """Validate a complete batch before returning any adapter payload."""
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"embeddings length ({len(embeddings)}) must match chunks length ({len(chunks)})"
        )
    dimension: int | None = None
    validated: list[list[float]] = []
    for index, vector in enumerate(embeddings):
        if not len(vector):
            raise ValueError(f"Embedding {index} must have a positive dimension")
        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            raise ValueError(f"Embedding {index} has dimension {len(vector)}; expected {dimension}")
        row: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"Embedding {index} must contain finite real numbers")
            try:
                number = float(value)
            except (ValueError, OverflowError) as exc:
                raise ValueError(f"Embedding {index} must contain finite real numbers") from exc
            # These vendor APIs store dense vectors as float32. Finite Python
            # floats can overflow during conversion and must fail before I/O.
            if not math.isfinite(number):
                raise ValueError(f"Embedding {index} must contain finite real numbers")
            if abs(number) > 3.4028234663852886e38:
                raise ValueError(f"Embedding {index} must contain finite float32 real numbers")
            row.append(number)
        validated.append(row)
    return validated


def weaviate_object_id(chunk_id: str) -> str:
    """Map a stable chunk ID to its Weaviate UUID, also for incremental deletions."""
    return str(uuid5(NAMESPACE_URL, f"omnichunk:{chunk_id}"))


def stable_chunk_id(chunk: Chunk, filepath: str | None = None) -> str:
    """Identify a content-anchored occurrence within a logical document.

    V2 identity excludes byte offsets, chunk index, configuration and rendered
    context, so an unchanged block can move without changing its ID. Equal raw
    blocks are disambiguated by their source-order ``occurrence``. A rename
    preserves identity only when the caller preserves ``source.source_id``.
    Legacy/manual chunks without a source descriptor use ``index`` to distinguish
    repeats. Rebuild old vector indexes; the v1 positional ID is not reused.
    """
    source_id = (
        filepath
        if filepath is not None
        else (chunk.source.source_id if chunk.source is not None else chunk.context.filepath)
    )
    occurrence = chunk.occurrence if chunk.source is not None else chunk.index
    return _fingerprint(
        ["omnichunk-occurrence-v2", source_id, chunk_content_fingerprint(chunk), occurrence]
    )


def chunk_content_fingerprint(chunk: Chunk) -> str:
    """SHA-256 of the exact raw UTF-8 text, independent of its location."""
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()


def chunk_embedding_fingerprint(chunk: Chunk) -> str:
    """Fingerprint payload and configuration for embedding invalidation.

    Source revision and offsets are deliberately excluded: an unrelated edit
    must not invalidate a byte-identical payload. External embedding model
    versioning must additionally be tracked by the embedding/indexing client.
    """
    return _fingerprint(
        [
            "omnichunk-embedding-v2",
            chunk_content_fingerprint(chunk),
            chunk.contextualized_text,
            chunk.config_fingerprint,
        ]
    )


def _fingerprint(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_vector_id(chunk: Chunk) -> str:
    return stable_chunk_id(chunk)


def _vectordb_metadata(chunk: Chunk, *, use_contextualized_text: bool) -> dict[str, Any]:
    text = chunk.contextualized_text if use_contextualized_text else chunk.text
    return {
        "text": text,
        "chunk_id": stable_chunk_id(chunk),
        "content_fingerprint": chunk_content_fingerprint(chunk),
        "embedding_fingerprint": chunk_embedding_fingerprint(chunk),
        "config_fingerprint": chunk.config_fingerprint,
        "source_id": chunk.source.source_id if chunk.source else chunk.context.filepath,
        "source_revision": chunk.source.revision if chunk.source else "",
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
        "omnichunk": _chunk_snapshot(chunk),
        "chunk_id": stable_chunk_id(chunk),
        "content_fingerprint": chunk_content_fingerprint(chunk),
        "embedding_fingerprint": chunk_embedding_fingerprint(chunk),
        "config_fingerprint": chunk.config_fingerprint,
        "source_id": chunk.source.source_id if chunk.source else chunk.context.filepath,
        "source_revision": chunk.source.revision if chunk.source else "",
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
        return {field.name: _to_serializable(getattr(value, field.name)) for field in fields(value)}

    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_to_serializable(item) for item in value]

    if isinstance(value, tuple):
        return [_to_serializable(item) for item in value]

    return value
