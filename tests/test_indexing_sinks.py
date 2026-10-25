"""Exercise real Qdrant local SDK and optional real PostgreSQL/pgvector writes."""

from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from omnichunk.indexing.models import (
    DeliveryBatch,
    PermanentSinkError,
    RetryableSinkError,
    VectorRecord,
)
from omnichunk.indexing.sinks import PgvectorSink, QdrantSink, qdrant_point_id


def record(key="same-id", *, text="policy", metadata=None):
    return VectorRecord(
        key, "source", "revision-1", text, metadata or {"acl": ["staff"]}, (1.0, 0.0)
    )


def batch(*, collection="tenant-a", upserts=(), deletes=()):
    return DeliveryBatch(
        collection,
        "test-target",
        "operation-key",
        tuple(upserts),
        tuple(deletes),
        tuple(f"op-{index}" for index in range(len(upserts) + len(deletes))),
    )


@pytest.fixture
def qdrant():
    module = pytest.importorskip("qdrant_client")
    models = pytest.importorskip("qdrant_client.models")
    client = module.QdrantClient(":memory:")
    client.create_collection(
        "test", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    yield client, QdrantSink(client, target_id="test-target", collection_name="test", dimensions=2)
    client.close()


def test_qdrant_replay_scoped_delete_and_acl_filter(qdrant):
    client, sink = qdrant
    models = pytest.importorskip("qdrant_client.models")
    item = record(metadata={"acl": ["staff"], "page": 3, "nested": {"language": "日本語"}})
    request = batch(upserts=[item])
    assert sink.apply(request).operation_ids == request.operation_ids
    sink.apply(request)  # A remote success followed by a lost journal ack is safe to replay.
    sink.apply(batch(collection="tenant-b", upserts=[item]))
    points, _ = client.scroll("test", limit=10)
    assert len(points) == 2
    scoped = models.Filter(
        must=[
            models.FieldCondition(key="collection", match=models.MatchValue(value="tenant-a")),
            models.FieldCondition(key="metadata.acl", match=models.MatchValue(value="staff")),
        ]
    )
    found = client.query_points("test", query=[1.0, 0.0], query_filter=scoped).points
    assert len(found) == 1
    assert found[0].payload["metadata"] == item.metadata
    sink.apply(batch(deletes=[item.id]))
    sink.apply(batch(deletes=[item.id]))
    points, _ = client.scroll("test", limit=10)
    assert [point.id for point in points] == [qdrant_point_id("tenant-b", item.id)]


def test_qdrant_metadata_refresh_replaces_old_acl(qdrant):
    client, sink = qdrant
    sink.apply(batch(upserts=[record()]))
    sink.apply(batch(upserts=[record(metadata={"acl": ["owner"], "page": 4})]))
    points, _ = client.scroll("test", limit=10)
    assert points[0].payload["metadata"] == {"acl": ["owner"], "page": 4}


@pytest.mark.parametrize(
    "embedding",
    [
        (1.0,),
        (float("nan"), 0.0),
        (True, 0.0),
        (float("inf"), 0.0),
        (1e300, 0.0),
        (-1e300, 0.0),
    ],
)
def test_invalid_vector_fails_before_qdrant_deletion(qdrant, embedding):
    client, sink = qdrant
    sink.apply(batch(upserts=[record()]))
    with pytest.raises(PermanentSinkError):
        sink.apply(
            batch(deletes=["same-id"], upserts=[replace(record("bad"), embedding=embedding)])
        )
    assert client.count("test").count == 1


def test_qdrant_requires_completed_result_and_classifies_timeout():
    pytest.importorskip("qdrant_client")
    client = SimpleNamespace(upsert=lambda **_: SimpleNamespace(status="acknowledged"))
    sink = QdrantSink(client, target_id="test-target", collection_name="test", dimensions=2)
    with pytest.raises(RetryableSinkError, match="completed"):
        sink.apply(batch(upserts=[record()]))

    def timeout(**_):
        raise TimeoutError("temporary")

    client.upsert = timeout
    with pytest.raises(RetryableSinkError, match="TimeoutError"):
        sink.apply(batch(upserts=[record()]))


def test_sink_rejects_wrong_target_before_network():
    sink = QdrantSink(None, target_id="other", collection_name="test", dimensions=2)
    with pytest.raises(PermanentSinkError, match="target"):
        sink.apply(batch(upserts=[record()]))


@pytest.mark.parametrize(
    "change",
    [
        {"operation_ids": ()},
        {"operation_ids": ("",)},
        {"operation_ids": ("repeat", "repeat"), "deletes": ("other",)},
        {"deletes": ("duplicate", "duplicate"), "operation_ids": ("a", "b", "c")},
        {"upserts": (record(), record()), "operation_ids": ("a", "b")},
    ],
)
def test_batch_operation_identity_is_validated_before_network(change):
    sink = QdrantSink(None, target_id="test-target", collection_name="test", dimensions=2)
    with pytest.raises(PermanentSinkError):
        sink.apply(replace(batch(upserts=[record()]), **change))


@pytest.mark.parametrize("error_name", ["ReadTimeout", "ConnectTimeout", "ReadError"])
def test_qdrant_wrapped_transport_timeout_is_retryable(error_name):
    exceptions = pytest.importorskip("qdrant_client.http.exceptions")
    httpx = pytest.importorskip("httpx")

    def timeout(**_):
        raise exceptions.ResponseHandlingException(getattr(httpx, error_name)("temporary"))

    sink = QdrantSink(
        SimpleNamespace(upsert=timeout),
        target_id="test-target",
        collection_name="test",
        dimensions=2,
    )
    with pytest.raises(RetryableSinkError):
        sink.apply(batch(upserts=[record()]))


def test_qdrant_delete_then_replace_same_id(qdrant):
    client, sink = qdrant
    sink.apply(batch(upserts=[record()]))
    sink.apply(batch(upserts=[record(text="replacement")], deletes=["same-id"]))
    points, _ = client.scroll("test")
    assert len(points) == 1 and points[0].payload["text"] == "replacement"


@pytest.mark.parametrize(
    "status,retryable",
    [
        ("UNAVAILABLE", True),
        ("DEADLINE_EXCEEDED", True),
        ("RESOURCE_EXHAUSTED", True),
        ("ABORTED", True),
        ("PERMISSION_DENIED", False),
        ("INVALID_ARGUMENT", False),
    ],
)
def test_qdrant_grpc_error_classification(status, retryable):
    pytest.importorskip("qdrant_client")
    grpc = pytest.importorskip("grpc")

    class RpcFailure(grpc.RpcError):
        def code(self):
            return getattr(grpc.StatusCode, status)

    def fail(**_):
        raise RpcFailure()

    sink = QdrantSink(
        SimpleNamespace(upsert=fail),
        target_id="test-target",
        collection_name="test",
        dimensions=2,
    )
    with pytest.raises(RetryableSinkError if retryable else PermanentSinkError):
        sink.apply(batch(upserts=[record()]))


@pytest.mark.parametrize("value", [1e300, -1e300])
def test_pgvector_float32_overflow_fails_before_accessing_connection(value):
    sink = PgvectorSink(None, target_id="test-target", dimensions=2)
    with pytest.raises(PermanentSinkError, match="float32"):
        sink.apply(batch(upserts=[replace(record(), embedding=(value, 0.0))], deletes=["old"]))


@pytest.mark.parametrize("dimensions", [0, -1, True, 1.5])
def test_sink_dimensions_are_positive_integers(dimensions):
    with pytest.raises(ValueError, match="dimensions"):
        QdrantSink(None, target_id="test", collection_name="test", dimensions=dimensions)
    with pytest.raises(ValueError, match="dimensions"):
        PgvectorSink(None, target_id="test", dimensions=dimensions)


def test_pgvector_rejects_ambiguous_table_names():
    with pytest.raises(ValueError, match="table"):
        PgvectorSink(None, target_id="test", dimensions=2, table="records; DROP TABLE users")


@pytest.fixture
def pgvector():
    dsn = os.environ.get("OMNICHUNK_PGVECTOR_DSN")
    if not dsn:
        pytest.skip("Set OMNICHUNK_PGVECTOR_DSN for real PostgreSQL/pgvector integration")
    psycopg = pytest.importorskip("psycopg")
    sql = pytest.importorskip("psycopg.sql")
    connection = psycopg.connect(dsn, autocommit=True)
    table = "omnichunk_test_" + uuid4().hex
    sink = PgvectorSink(connection, target_id="test-target", dimensions=2, table=table)
    sink.initialize()
    yield connection, sink
    connection.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(table)))
    connection.close()


def test_pgvector_replay_delete_isolation_and_acl_filter(pgvector):
    connection, sink = pgvector
    sql = pytest.importorskip("psycopg.sql")
    item = record(metadata={"acl": ["staff"], "page": 3, "nested": {"lang": "日本語"}})
    request = batch(upserts=[item])
    assert sink.apply(request).idempotency_key == request.idempotency_key
    sink.apply(request)
    sink.apply(batch(collection="tenant-b", upserts=[item]))
    found = connection.execute(
        sql.SQL(
            "SELECT id,metadata FROM {} WHERE collection=%s AND metadata->'acl' ? %s "
            "ORDER BY embedding <=> %s::vector LIMIT 5"
        ).format(sql.Identifier(sink.table)),
        ("tenant-a", "staff", "[1,0]"),
    ).fetchall()
    assert found == [(item.id, item.metadata)]
    sink.apply(batch(deletes=[item.id]))
    sink.apply(batch(deletes=[item.id]))
    remaining = connection.execute(
        sql.SQL("SELECT collection,id FROM {}").format(sql.Identifier(sink.table))
    ).fetchall()
    assert remaining == [("tenant-b", item.id)]


def test_pgvector_failed_upsert_rolls_back_deletions(pgvector):
    connection, sink = pgvector
    sql = pytest.importorskip("psycopg.sql")
    sink.apply(batch(upserts=[record()]))
    connection.execute(
        sql.SQL("ALTER TABLE {} ADD CHECK (text <> 'reject')").format(sql.Identifier(sink.table))
    )
    with pytest.raises(PermanentSinkError):
        sink.apply(batch(deletes=["same-id"], upserts=[record("bad", text="reject")]))
    rows = connection.execute(
        sql.SQL("SELECT id FROM {}").format(sql.Identifier(sink.table))
    ).fetchall()
    assert rows == [("same-id",)]


def test_pgvector_metadata_refresh_and_outer_transaction_rejection(pgvector):
    connection, sink = pgvector
    sql = pytest.importorskip("psycopg.sql")
    sink.apply(batch(upserts=[record()]))
    sink.apply(batch(upserts=[record(metadata={"acl": ["owner"]})]))
    assert connection.execute(
        sql.SQL("SELECT metadata FROM {}").format(sql.Identifier(sink.table))
    ).fetchone()[0] == {"acl": ["owner"]}
    with connection.transaction(), pytest.raises(PermanentSinkError, match="idle"):
        sink.apply(batch(deletes=["same-id"]))


def test_pgvector_invalid_vector_does_not_delete(pgvector):
    connection, sink = pgvector
    sql = pytest.importorskip("psycopg.sql")
    sink.apply(batch(upserts=[record()]))
    with pytest.raises(PermanentSinkError, match="dimension"):
        sink.apply(batch(deletes=["same-id"], upserts=[replace(record("bad"), embedding=(1.0,))]))
    assert (
        connection.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(sink.table))
        ).fetchone()[0]
        == 1
    )
