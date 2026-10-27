# Omnichunk

Build retrieval chunks with verifiable source locations, explicit size limits and
enough structure to preserve the meaning of code and documents. Omnichunk is a
Python library for the chunking stage of a RAG pipeline. Your application chooses
the embedding model, retrieval backend and answer generator.

## First chunks

```bash
pip install omnichunk
```

The examples on this site describe the repository's current API. For unreleased
changes, install a checkout with `pip install -e .`; use the
[migration guide](migrations/v2.md) when upgrading an existing index.

```python
from omnichunk import Chunker

source = "# Retention policy\n\nCustomer backups expire after 30 days.\n"
chunker = Chunker(max_chunk_size=256, size_unit="chars")
chunks = chunker.chunk("policies/retention.md", source)

for chunk in chunks:
    # Embed this payload; its rendered context also fits the configured limit.
    assert len(chunk.contextualized_text) <= 256
    print(chunk.contextualized_text)

    # Cite the original text, with zero-based, half-open UTF-8 byte coordinates.
    start, end = chunk.byte_range.start, chunk.byte_range.end
    assert source.encode("utf-8")[start:end].decode("utf-8") == chunk.text
```

Character sizing is the default. For a model token limit, install a compatible
tokenizer and configure it explicitly:

```bash
pip install "omnichunk[tiktoken]"
```

```python
chunker = Chunker(max_chunk_size=512, size_unit="tokens", tokenizer="cl100k_base")
```

Choose the tokenizer used by your embedding model. Reserve additional space for
prompt instructions, citation labels and separators when assembling LLM context.
See the [source and budget contracts](reference/contracts.md) for overlap,
lossless reconstruction, overflow and token accuracy.

## Choose a workflow

| You need | Start with |
| --- | --- |
| Practical chunking, files, streaming, hierarchy and diffs | [Chunking recipes](usage.md) |
| Every chunk setting, accepted values and defaults | [Chunk options](reference/options.md) |
| Types, classes, methods and function signatures | [Python API reference](reference/chunker.md) |
| A local retrieval pipeline with updates, deletions and citations | [Index, retrieve and synchronize](indexing.md) |
| AST boundaries and code entities | Install `omnichunk[code]`; inspect `language_capabilities()` for actual parser support. |
| PDF, DOCX or notebooks | [Install format extras](install.md), use `chunk_file()`, and retain canonical extracted text for citations. |
| Semantic boundaries | Supply an embedding callback; see the [runnable examples](https://github.com/oguzhankir/omnichunk/tree/main/examples). |
| Parent context, diffs, framework conversion or vector export | [Python API](reference/chunker.md) and [examples](https://github.com/oguzhankir/omnichunk/tree/main/examples) |
| Reproducible evaluation | [Performance methodology](performance/sla.md) |
| A safe upgrade of a persisted index | [Migration guide](migrations/v2.md) |

## What to evaluate before adoption

The base install has no mandatory third-party dependencies. Optional parsers,
tokenizers and loaders affect capabilities and output; pin them with the chunking
configuration for reproducible index generations. Streaming yields chunks but
still retains source and parser state. SQLite synchronization is atomic locally;
delivery to an external vector database is the application's responsibility.

Retrieval quality depends on your corpus, queries, embedding model and retriever.
Omnichunk does not currently establish a cross-corpus quality lead or universal
throughput SLA. The [roadmap](https://github.com/oguzhankir/omnichunk/blob/main/ROADMAP.md)
defines the evidence and production capabilities needed to earn that position.

[API stability](api-stability.md) ·
[Changelog](https://github.com/oguzhankir/omnichunk/blob/main/CHANGELOG.md) ·
[Source and issues](https://github.com/oguzhankir/omnichunk)
