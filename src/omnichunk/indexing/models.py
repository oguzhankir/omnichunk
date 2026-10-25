"""Versioned, dependency-free indexing plans and acknowledgement contracts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from numbers import Real
from typing import Any, Protocol

from omnichunk.types import Chunk


class IndexConflictError(ValueError):
    """A plan no longer matches the collection generation or pending delivery."""


class JournalSchemaError(ValueError):
    """The database is not a supported indexing journal."""


class RetryableSinkError(RuntimeError):
    """Delivery failed transiently and can be retried by the next deliver call."""


class PermanentSinkError(RuntimeError):
    """Delivery needs intervention before an explicit retry_failed=True call."""


class AcknowledgementError(PermanentSinkError):
    """A sink did not acknowledge exactly the submitted batch."""


def json_value(value: Any) -> Any:
    """Deep-copy JSON values, refusing coercions, NaN and non-string object keys."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    raise ValueError("Index metadata must contain finite JSON values")


def canonical_json(value: Any) -> str:
    return json.dumps(
        json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def name(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def embedding_key(text: str, model_revision: str, preprocessing_revision: str) -> str:
    return digest(["omnichunk-index-embedding-v1", text, model_revision, preprocessing_revision])


def vector_values(value: Any, dimension: int | None = None) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        try:
            value = list(value)
        except TypeError as exc:
            raise ValueError("Embedding must be a finite vector") from exc
    if not value:
        raise ValueError("Embedding must have positive dimension")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise ValueError("Embedding must contain finite real numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("Embedding must contain finite real numbers")
        result.append(number)
    if dimension is not None and len(result) != dimension:
        raise ValueError(
            f"Embedding dimension {len(result)} differs from collection dimension {dimension}"
        )
    return tuple(result)


@dataclass(frozen=True)
class IndexSource:
    source_id: str
    revision: str
    chunks: tuple[Chunk, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexRecord:
    id: str
    source_id: str
    source_revision: str
    text: str
    metadata: dict[str, Any]
    embedding_key: str


@dataclass(frozen=True)
class VectorRecord:
    id: str
    source_id: str
    source_revision: str
    text: str
    metadata: dict[str, Any]
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class DeliveryBatch:
    collection: str
    target_id: str
    idempotency_key: str
    upserts: tuple[VectorRecord, ...]
    deletes: tuple[str, ...]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryReceipt:
    idempotency_key: str
    operation_ids: tuple[str, ...]


class IndexSink(Protocol):
    target_id: str

    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt: ...


@dataclass(frozen=True)
class IndexStatus:
    collection: str
    generation: int
    pending_plan_id: str | None
    pending_operations: int
    acknowledged_operations: int
    last_error: str | None
    retryable: bool


@dataclass(frozen=True)
class DeliveryResult:
    plan_id: str | None
    acknowledged: int
    pending: int
    completed: bool
    embedding_calls: int
    reused_embeddings: int


@dataclass(frozen=True)
class IndexPlan:
    collection: str
    target_id: str
    base_generation: int
    model_revision: str
    preprocessing_revision: str
    use_contextualized_text: bool
    source_revisions: tuple[tuple[str, str], ...]
    deleted_sources: tuple[str, ...]
    upserts: tuple[IndexRecord, ...]
    removed_ids: tuple[str, ...]
    added_ids: tuple[str, ...]
    metadata_update_ids: tuple[str, ...]
    embedding_invalidations: tuple[str, ...]
    unchanged_ids: tuple[str, ...]
    scope: str | None = None
    complete_scope: bool = False
    scope_source_ids: tuple[str, ...] = ()
    plan_id: str = ""
    schema_version: int = 1

    def _body(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("plan_id")
        return result

    def to_json(self) -> str:
        """Serialize an integrity-checked plan; post-creation mutation is rejected."""
        value = {**self._body(), "plan_id": self.plan_id}
        self.from_dict(value)
        return canonical_json(value)

    @classmethod
    def from_json(cls, value: str) -> IndexPlan:
        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in items:
                if key in result:
                    raise ValueError("Duplicate plan JSON key")
                result[key] = item
            return result

        return cls.from_dict(json.loads(value, object_pairs_hook=pairs))

    @classmethod
    def from_dict(cls, value: Any) -> IndexPlan:
        value = json_value(value)
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Invalid index plan fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported index plan schema")
        for key in (
            "collection",
            "target_id",
            "model_revision",
            "preprocessing_revision",
            "plan_id",
        ):
            name(value[key], key)
        if type(value["base_generation"]) is not int or value["base_generation"] < 0:
            raise ValueError("Invalid plan generation")
        for key in ("use_contextualized_text", "complete_scope"):
            if type(value[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
        if value["scope"] is not None:
            name(value["scope"], "scope")
        elif value["complete_scope"] or value["scope_source_ids"]:
            raise ValueError("Scope membership requires a scope")
        source_revisions = value["source_revisions"]
        if not isinstance(source_revisions, list):
            raise ValueError("Invalid source revisions")
        sources: dict[str, str] = {}
        for pair in source_revisions:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Invalid source revision pair")
            source, revision = name(pair[0], "source_id"), name(pair[1], "revision")
            if source in sources:
                raise ValueError("Duplicate source ID")
            sources[source] = revision
        tuple_fields = (
            "deleted_sources",
            "removed_ids",
            "added_ids",
            "metadata_update_ids",
            "embedding_invalidations",
            "unchanged_ids",
            "scope_source_ids",
        )
        for key in tuple_fields:
            items = value[key]
            if (
                not isinstance(items, list)
                or any(not isinstance(item, str) or not item.strip() for item in items)
                or len(set(items)) != len(items)
            ):
                raise ValueError(f"Invalid or duplicate {key}")
            value[key] = tuple(items)
        if set(sources) & set(value["deleted_sources"]):
            raise ValueError("A source cannot be updated and deleted in one plan")
        if set(value["scope_source_ids"]) != (set(sources) if value["scope"] else set()):
            raise ValueError("Scope source membership differs from updated sources")
        records = []
        if not isinstance(value["upserts"], list):
            raise ValueError("Invalid upserts")
        ids: set[str] = set()
        for raw in value["upserts"]:
            if not isinstance(raw, dict) or set(raw) != set(IndexRecord.__dataclass_fields__):
                raise ValueError("Invalid index record fields")
            for key in ("id", "source_id", "source_revision", "embedding_key"):
                name(raw[key], key)
            if not isinstance(raw["text"], str) or not isinstance(raw["metadata"], dict):
                raise ValueError("Invalid index record payload")
            if raw["id"] in ids or sources.get(raw["source_id"]) != raw["source_revision"]:
                raise ValueError("Duplicate record or mismatched source ownership")
            if raw["embedding_key"] != embedding_key(
                raw["text"], value["model_revision"], value["preprocessing_revision"]
            ):
                raise ValueError("Embedding fingerprint does not match the payload")
            ids.add(raw["id"])
            records.append(IndexRecord(**raw))
        categories = [
            set(value[key])
            for key in ("added_ids", "metadata_update_ids", "embedding_invalidations")
        ]
        if set().union(*categories) != ids or sum(map(len, categories)) != len(ids):
            raise ValueError("Upsert classifications must partition the upserts")
        if (ids & (set(value["removed_ids"]) | set(value["unchanged_ids"]))) or (
            set(value["removed_ids"]) & set(value["unchanged_ids"])
        ):
            raise ValueError("Record actions overlap")
        plan_id = value.pop("plan_id")
        if digest(value) != plan_id:
            raise ValueError("Index plan digest does not match its contents")
        value["upserts"] = tuple(records)
        value["source_revisions"] = tuple(tuple(pair) for pair in source_revisions)
        return cls(**value, plan_id=plan_id)
