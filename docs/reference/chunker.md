# Python API

These sections are generated from source docstrings by `mkdocstrings`. For
behavioral guarantees and examples, read the [contracts](contracts.md) and
[indexing guide](../indexing.md).

## Chunking

::: omnichunk.chunker.Chunker

## Local index lifecycle

::: omnichunk.store.ChunkStore

::: omnichunk.store.SyncResult

## Recoverable index delivery

::: omnichunk.indexing.IndexSource

::: omnichunk.indexing.IndexPlan

::: omnichunk.indexing.IndexJournal

::: omnichunk.indexing.DeliveryBatch

::: omnichunk.indexing.DeliveryReceipt

::: omnichunk.indexing.DeliveryResult

## Optional native framework adapters

::: omnichunk.integrations.langchain.OmniChunkTextSplitter

::: omnichunk.integrations.llamaindex.OmniChunkNodeParser

::: omnichunk.integrations.llamaindex.OmniChunkIngestionPipeline

## Optional delivery sinks

::: omnichunk.indexing.sinks.QdrantSink

::: omnichunk.indexing.sinks.PgvectorSink

::: omnichunk.serialization.chunks_to_pinecone_upsert_request

## Durable chunk records and identity

::: omnichunk.serialization.chunk_to_dict

::: omnichunk.serialization.chunk_from_dict

::: omnichunk.serialization.stable_chunk_id

::: omnichunk.serialization.chunk_embedding_fingerprint
