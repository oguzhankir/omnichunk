"""Run with ``pip install -e '.[pgvector]'`` and OMNICHUNK_PGVECTOR_DSN.

Use a disposable database with permission to create the vector extension. This
recipe creates a unique table and drops it on exit. Keyword features exercise
the delivery/query contract; replace them with a selected embedding model.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import psycopg
from psycopg import sql

from omnichunk import Chunker
from omnichunk.indexing import IndexJournal, IndexSource
from omnichunk.indexing.sinks import PgvectorSink


def embed(texts: Sequence[str]) -> list[list[float]]:
    return [
        [float(text.lower().count("backup") + 1), float(text.lower().count("export") + 1)]
        for text in texts
    ]


def main() -> None:
    connection = psycopg.connect(os.environ["OMNICHUNK_PGVECTOR_DSN"], autocommit=True)
    table = "omnichunk_demo_" + uuid4().hex
    sink = PgvectorSink(connection, target_id="demo-pgvector:" + table, dimensions=2, table=table)
    sink.initialize()
    try:
        chunks = Chunker(context_mode="none").chunk(
            "backup.txt", "Backup retention is thirty days."
        )
        assert chunks[0].source is not None
        source = IndexSource(
            chunks[0].source.source_id,
            chunks[0].source.revision,
            tuple(chunks),
            {"acl": ["support"]},
        )
        with (
            TemporaryDirectory() as temporary,
            IndexJournal(Path(temporary) / "delivery.sqlite") as journal,
        ):
            plan = journal.plan(
                [source],
                collection="tenant-a",
                target_id=sink.target_id,
                model_revision="demo-keywords-v1",
            )
            print("Dry-run plan:", plan.to_json())
            journal.enqueue(plan)
            assert journal.deliver(sink, embed, collection="tenant-a", batch_size=16).completed

            # Derive the requester group from application authentication. Include
            # both collection and ACL predicates in the database query.
            rows = connection.execute(
                sql.SQL(
                    "SELECT text, metadata FROM {} WHERE collection=%s AND metadata->'acl' ? %s "
                    "ORDER BY embedding <=> %s::vector LIMIT 5"
                ).format(sql.Identifier(table)),
                ("tenant-a", "support", "[2,1]"),
            ).fetchall()
            assert len(rows) == 1
            print("Authorized result:", rows[0][0])
            print("Canonical citation:", rows[0][1]["omnichunk"]["byte_range"])
            deletion = journal.plan(
                [],
                collection="tenant-a",
                target_id=sink.target_id,
                model_revision="demo-keywords-v1",
                delete_sources=[source.source_id],
            )
            journal.enqueue(deletion)
            assert journal.deliver(sink, collection="tenant-a").completed
            assert (
                connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()[0]
                == 0
            )
    finally:
        connection.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(table)))
        connection.close()


if __name__ == "__main__":
    main()
