OmniChunk 2.2.0 adds recoverable indexing and native RAG integrations, backed by reproducible retrieval evaluation.

## Highlights

- **Recoverable indexing:** versioned dry-run plans, durable embedding reuse, acknowledged Qdrant/pgvector delivery, explicit deletes and restart recovery.
- **Native integrations:** LangChain splitter, LlamaIndex parser and an identity-safe ingestion pipeline. Pinecone request envelopes preserve complete metadata.
- **Better chunk boundaries:** Unicode-aware prose splitting and configured character/token budgets for code, including multibyte declarations.
- **Reproducible evaluation:** seven chunker adapters, 300 multilingual synthetic questions and 96 human-annotated SQuAD questions, exact source-span metrics, frozen dense artifacts and local-model preparation.
- **Correctness fixes:** stale imported payloads, cross-source cache reuse, transient gRPC retries, float32 overflow and lossy filter metadata.

## Install

```bash
pip install --upgrade omnichunk==2.2.0
# Optional integrations:
pip install 'omnichunk[langchain,llamaindex,qdrant,pgvector]==2.2.0'
```

PyPI availability follows the validated publication workflow. The dependency-free core remains available without integration extras.

## Upgrade and operating contract

Use a separate IndexJournal database and validate a new remote target before switching readers; keep the previous index for rollback. Delivery is at least once and intermediate remote changes can be visible before a plan completes. Applications own retrieval authorization. Use OmniChunkIngestionPipeline for cached native LlamaIndex ingestion.

Named tokenizers fail explicitly when unavailable; vector exports reject values that overflow float32. Pinecone numeric filter identifiers must preserve float64 precision; use strings for large IDs.

## Evidence and scope

1,314 local tests passed with 91.03% branch coverage; all 12 PR CI jobs passed, including minimum/current integrations and real PostgreSQL/pgvector. Release artifacts undergo fresh validation.

The small external English-prose benchmark has ties and losses: OmniChunk reaches 0.9792 held-out evidence recall at 256-character chunks, tied with several alternatives. No pretrained dense-model leadership claim is made. Pretrained multilingual evaluation and production design-partner validation remain open.

See the [indexing guide](https://oguzhankir.github.io/omnichunk/indexing/), [changelog](https://github.com/oguzhankir/omnichunk/blob/main/CHANGELOG.md), and [benchmark methodology](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/README.md). The attributed SQuAD corpus and reproduced passages are CC-BY-SA-4.0; the library is MIT licensed.
