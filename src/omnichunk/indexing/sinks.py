"""Optional synchronous vector sinks with scoped, idempotent record writes.

Clients/connections and remote provisioning remain caller-owned. A receipt means
all operations completed; a crash between remote completion and journal receipt
can replay the same writes. This is at-least-once delivery, not a distributed
transaction or an authorization boundary.
"""

from __future__ import annotations

import importlib
import json
import math
import re
from numbers import Real
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .models import DeliveryBatch, DeliveryReceipt, PermanentSinkError, RetryableSinkError

_FLOAT32_MAX = 3.4028234663852886e38


def qdrant_point_id(collection: str, record_id: str) -> str:
    """Map a logical collection/record pair to the UUID used for writes/deletes."""
    return str(uuid5(NAMESPACE_URL, json.dumps(["omnichunk-index-v1", collection, record_id])))


def _dimension(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("dimensions must be a positive integer")
    return value


def _name(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _json_copy(value: Any) -> Any:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("metadata keys must be strings")
        return {key: _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("metadata must contain only finite JSON values")


def _validate_batch(batch: DeliveryBatch, target_id: str, dimensions: int) -> None:
    if batch.target_id != target_id:
        raise PermanentSinkError("Delivery target does not match the configured sink")
    try:
        _name(batch.collection, "collection")
        _name(batch.idempotency_key, "idempotency_key")
        if len(batch.operation_ids) != len(batch.upserts) + len(batch.deletes):
            raise ValueError("operation_ids must identify every upsert and deletion")
        for operation_id in batch.operation_ids:
            _name(operation_id, "operation id")
        if len(set(batch.operation_ids)) != len(batch.operation_ids):
            raise ValueError("operation_ids must be unique")
        if len(set(batch.deletes)) != len(batch.deletes):
            raise ValueError("Deletion IDs must be unique")
        if len({record.id for record in batch.upserts}) != len(batch.upserts):
            raise ValueError("Upsert IDs must be unique")
        for record_id in batch.deletes:
            _name(record_id, "record id")
        for record in batch.upserts:
            _name(record.id, "record id")
            _name(record.source_id, "source id")
            _name(record.source_revision, "source revision")
            if not isinstance(record.text, str) or not isinstance(record.metadata, dict):
                raise ValueError("record text/metadata must be a string/object")
            _json_copy(record.metadata)
            if len(record.embedding) != dimensions:
                raise ValueError(f"Embedding dimension must equal {dimensions}")
            if any(
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                or abs(float(value)) > _FLOAT32_MAX
                for value in record.embedding
            ):
                raise ValueError("Embeddings must contain finite float32 real numbers")
    except (ValueError, TypeError, OverflowError) as exc:
        raise PermanentSinkError(str(exc)) from exc


def _delivery_error(exc: Exception, vendor: str) -> Exception:
    if isinstance(exc, (RetryableSinkError, PermanentSinkError)):
        return exc
    # Qdrant's HTTP transport wraps its original httpx exception in ``source``.
    cause = getattr(exc, "source", None)
    if not isinstance(cause, Exception):
        cause = exc
    status = getattr(cause, "status_code", None)
    sqlstate = getattr(cause, "sqlstate", None)
    # Qdrant also supports gRPC. Inspect its optional exception hierarchy without
    # importing grpc when only the dependency-free core or pgvector is in use.
    grpc_status = None
    if any(cls.__name__ == "RpcError" and cls.__module__ == "grpc" for cls in type(cause).__mro__):
        code = getattr(cause, "code", None)
        if callable(code):
            grpc_status = getattr(code(), "name", None)
    transient = (
        isinstance(cause, (ConnectionError, TimeoutError))
        or status == 429
        or (isinstance(status, int) and status >= 500)
        or (isinstance(sqlstate, str) and sqlstate[:2] in {"08", "40"})
        or sqlstate in {"55P03", "53300", "57P01", "57P02", "57P03"}
        or grpc_status in {"UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED", "ABORTED"}
        or any(
            cls.__module__.startswith("httpx") and cls.__name__ == "TransportError"
            for cls in type(cause).__mro__
        )
    )
    error_type = RetryableSinkError if transient else PermanentSinkError
    return error_type(f"{vendor} delivery failed ({type(exc).__name__}): {exc}")


class QdrantSink:
    """Write to a caller-provisioned Qdrant collection using qdrant-client 1.x.

    The collection must have a single unnamed dense vector of ``dimensions``.
    Logical index collections share the physical collection safely through UUID
    mapping. Retrieval must filter both ``collection`` and caller-owned access
    attributes, for example ``metadata.acl``. ``target_id`` must permanently
    identify this endpoint and physical collection in the application's journal.
    If one ID occurs in both deletes and upserts, deletion precedes replacement.
    """

    def __init__(
        self, client: Any, *, target_id: str, collection_name: str, dimensions: int
    ) -> None:
        self.client = client
        self.target_id = _name(target_id, "target_id")
        self.collection_name = _name(collection_name, "collection_name")
        self.dimensions = _dimension(dimensions)

    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt:
        _validate_batch(batch, self.target_id, self.dimensions)
        models = importlib.import_module("qdrant_client.models")
        # Validate/construct every point before any deletion is sent.
        points = [
            models.PointStruct(
                id=qdrant_point_id(batch.collection, record.id),
                vector=[float(value) for value in record.embedding],
                payload={
                    "collection": batch.collection,
                    "record_id": record.id,
                    "source_id": record.source_id,
                    "source_revision": record.source_revision,
                    "text": record.text,
                    "metadata": _json_copy(record.metadata),
                },
            )
            for record in batch.upserts
        ]
        try:
            if batch.deletes:
                result = self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.PointIdsList(
                        points=[qdrant_point_id(batch.collection, key) for key in batch.deletes]
                    ),
                    wait=True,
                )
                self._require_completed(result)
            if points:
                result = self.client.upsert(
                    collection_name=self.collection_name, points=points, wait=True
                )
                self._require_completed(result)
        except Exception as exc:
            if isinstance(exc, (RetryableSinkError, PermanentSinkError)):
                raise
            raise _delivery_error(exc, "Qdrant") from exc
        return DeliveryReceipt(batch.idempotency_key, batch.operation_ids)

    @staticmethod
    def _require_completed(result: Any) -> None:
        status = getattr(result, "status", None)
        if getattr(status, "value", status) != "completed":
            raise RetryableSinkError("Qdrant did not confirm completed durable operations")


class PgvectorSink:
    """Commit collection-scoped writes through a caller-owned psycopg 3 connection.

    Call ``initialize()`` explicitly to create the vector extension and table.
    The connection must be idle at entry so a receipt cannot precede an outer
    transaction's commit. Use autocommit connections for application reads.
    ``target_id`` must identify the database/schema/table in the journal.
    """

    def __init__(
        self,
        connection: Any,
        *,
        target_id: str,
        dimensions: int,
        table: str = "omnichunk_vectors",
    ) -> None:
        self.connection = connection
        self.target_id = _name(target_id, "target_id")
        self.dimensions = _dimension(dimensions)
        if not isinstance(table, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,62}", table):
            raise ValueError("table must be an unqualified SQL identifier of at most 63 characters")
        self.table = table

    def _require_idle(self) -> None:
        # psycopg.pq.TransactionStatus.IDLE has value zero.
        if self.connection.info.transaction_status != 0:
            raise PermanentSinkError("Pgvector delivery requires an idle connection")

    def initialize(self) -> None:
        """Explicitly provision the extension/table; requires database privileges."""
        self._require_idle()
        sql = importlib.import_module("psycopg.sql")
        with self.connection.transaction():
            self.connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.connection.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {} ("
                    "collection TEXT NOT NULL, id TEXT NOT NULL, source_id TEXT NOT NULL, "
                    "source_revision TEXT NOT NULL, text TEXT NOT NULL, metadata JSONB NOT NULL, "
                    "embedding vector({}) NOT NULL, PRIMARY KEY (collection, id))"
                ).format(sql.Identifier(self.table), sql.Literal(self.dimensions))
            )

    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt:
        _validate_batch(batch, self.target_id, self.dimensions)
        self._require_idle()
        sql = importlib.import_module("psycopg.sql")
        # Build JSON/vector parameters before opening the remote transaction.
        rows = [
            (
                batch.collection,
                record.id,
                record.source_id,
                record.source_revision,
                record.text,
                json.dumps(_json_copy(record.metadata), ensure_ascii=False, allow_nan=False),
                "[" + ",".join(str(float(value)) for value in record.embedding) + "]",
            )
            for record in batch.upserts
        ]
        try:
            with self.connection.transaction():
                if batch.deletes:
                    self.connection.execute(
                        sql.SQL("DELETE FROM {} WHERE collection = %s AND id = ANY(%s)").format(
                            sql.Identifier(self.table)
                        ),
                        (batch.collection, list(batch.deletes)),
                    )
                if rows:
                    with self.connection.cursor() as cursor:
                        cursor.executemany(
                            sql.SQL(
                                "INSERT INTO {} (collection,id,source_id,source_revision,text,"
                                "metadata,embedding) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::vector) "
                                "ON CONFLICT (collection,id) DO UPDATE SET "
                                "source_id=EXCLUDED.source_id,source_revision=EXCLUDED.source_revision,"
                                "text=EXCLUDED.text,metadata=EXCLUDED.metadata,embedding=EXCLUDED.embedding"
                            ).format(sql.Identifier(self.table)),
                            rows,
                        )
        except Exception as exc:
            raise _delivery_error(exc, "pgvector") from exc
        return DeliveryReceipt(batch.idempotency_key, batch.operation_ids)
