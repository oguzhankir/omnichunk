<div align="center">
  <picture>
    <source srcset="./assets/readme-hero.svg" type="image/svg+xml">
    <img src="https://raw.githubusercontent.com/oguzhankir/omnichunk/main/assets/readme-hero.png" alt="OmniChunk — code, documents, RAG" width="1200">
  </picture>

  <h1>Structure-aware chunking for reliable RAG.</h1>

  <p>Turn code and documents into traceable chunks.<br>Preserve useful structure, set explicit size budgets, and keep indexes in sync.</p>

  <a href="https://pypi.org/project/omnichunk/"><img src="https://img.shields.io/pypi/v/omnichunk?color=8973d7" alt="PyPI version"></a>
  <a href="https://github.com/oguzhankir/omnichunk/actions/workflows/ci.yml"><img src="https://github.com/oguzhankir/omnichunk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/oguzhankir/omnichunk"><img src="https://codecov.io/gh/oguzhankir/omnichunk/branch/main/graph/badge.svg?precision=2" alt="Test coverage"></a>
  <a href="https://pypi.org/project/omnichunk/"><img src="https://img.shields.io/pypi/pyversions/omnichunk?color=8973d7" alt="Supported Python versions"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/pypi/l/omnichunk?color=8973d7" alt="MIT license"></a>

  <p><a href="https://oguzhankir.github.io/omnichunk/"><strong>Documentation</strong></a> · <a href="#quick-start"><strong>Quick start</strong></a> · <a href="./examples/README.md"><strong>Examples</strong></a> · <a href="./CONTRIBUTING.md"><strong>Contribute</strong></a></p>
</div>

<br>

<picture>
  <source media="(max-width: 640px)" srcset="./assets/readme-workflow-mobile.svg">
  <source srcset="./assets/readme-workflow.svg" type="image/svg+xml">
  <img src="https://raw.githubusercontent.com/oguzhankir/omnichunk/main/assets/readme-workflow.png" alt="A Markdown document becomes two chunks: the heading and first paragraph at bytes [0, 40), then the second paragraph at [40, 63). Both retain the Retention heading as metadata." width="1200">
</picture>

## Why OmniChunk?

| Preserve structure | Trace every chunk | Control your index |
| :--- | :--- | :--- |
| Follow code declarations, document headings and paragraph boundaries. Retain scope and import context where supported. | Keep canonical UTF-8 source ranges, source identity and revision metadata alongside the retrieval payload. | Budget the final rendered payload. Detect edits, reuse unchanged embeddings and apply explicit index updates. |

**Local structural processing. No mandatory dependencies in the base install.**
Choose your own embedding model and retrieval backend; add parsers, tokenizers
and integrations as you need them.

## Quick start

Python 3.10+:

```bash
pip install omnichunk
```

```python
from omnichunk import Chunker

source = "# Retention\n\nKeep backups for 30 days.\n\nDelete expired copies.\n"
chunker = Chunker(max_chunk_size=48, size_unit="chars", context_mode="none")

for chunk in chunker.chunk("policy.md", source):
    print(chunk.byte_range.start, chunk.byte_range.end, repr(chunk.text))
```

```text
0 40 '# Retention\n\nKeep backups for 30 days.\n\n'
40 63 'Delete expired copies.\n'
```

Both chunks retain `Retention` in `chunk.context.heading_hierarchy`. Source
ranges address the original text; `chunk.contextualized_text` is the payload to
embed when you enable rendered context.

### Code and model tokens

Add AST parsers and a tokenizer when your workflow needs them:

```bash
pip install "omnichunk[code,tiktoken]"
```

```python
chunker = Chunker(
    max_chunk_size=512,
    size_unit="tokens",
    tokenizer="cl100k_base",
    context_mode="full",
)
```

Use the tokenizer that matches your downstream model. The default split policy
checks the complete rendered payload against the selected budget. Tokenizer
assets may download on first use; cache them for offline runs. See
[all options and defaults](docs/reference/options.md) and the
[source and budget contracts](docs/reference/contracts.md).

## Built for code and documents

| Input | What you can retain |
| :--- | :--- |
| **Source code** | AST boundaries, declarations, scopes, comments and import context. The `code` extra includes Python, JavaScript, TypeScript, Rust, Go and Java grammars. |
| **Markdown and prose** | Headings, paragraph boundaries, lists, tables and fenced code, with exact source locations. |
| **Structured documents** | Load notebooks, RST and LaTeX; add the `formats` extra for PDF/DOCX text extraction. Ranges refer to canonical extracted text. |

Additional grammars are available through `all-languages`. Parser availability
and extraction depth vary; `language_capabilities()` reports the installed
capabilities and diagnosed fallbacks. See [installation](docs/install.md) and
[runnable recipes](docs/usage.md) for format, semantic and boundary-policy options.

## Fits your retrieval stack

| Workflow | Integration |
| :--- | :--- |
| **LangChain** | Native `OmniChunkTextSplitter` with chunk IDs, metadata and source references. |
| **LlamaIndex** | Native nodes, hierarchy relationships and an identity-aware ingestion pipeline. |
| **Qdrant / pgvector** | Optional acknowledged sinks with resumable delivery through `IndexJournal`. |
| **Your own pipeline** | Plain Python chunks, sync/async/batch APIs, iterators, JSONL/CSV and vector payload exports. |

Follow the [indexing guide](docs/indexing.md) for adapters, cached ingestion and
recoverable updates, or browse the [API reference](https://oguzhankir.github.io/omnichunk/reference/chunker/).

### Keep a changing corpus in sync

```python
chunker = Chunker(max_chunk_size=256, context_mode="none")
previous = chunker.chunk("policy.txt", "Retain backups for 30 days.")
changes = chunker.chunk_diff("policy.txt", "Retain backups for 60 days.", previous_chunks=previous)

print(changes.removed_ids)  # Remove old records from your index.
print([chunk.text for chunk in changes.added])  # Embed and upsert new payloads.
```

Persistent workflows can use a SQLite delivery journal to resume pending writes
and reuse prepared vectors. Delivery is at least once; see
[delivery and recovery semantics](docs/indexing.md) before connecting a remote index.

## From the terminal

```bash
omnichunk ./src --glob "**/*.py" --max-size 512 --size-unit chars --format jsonl > chunks.jsonl
```

Use `chunk_file()` for individual files and structured loaders. See
[files, directories and CLI recipes](docs/usage.md) for more examples. Try the [local project search and RAG example](examples/README.md#search-your-own-project) to retrieve cited code and documentation.

## Measured, with the tradeoffs visible

The [evaluation guide](benchmarks/README.md) and
[published experiments](benchmarks/retrieval/reports/quality-v3/README.md) retain
source provenance, shared-budget comparisons, costs, wins and losses. Retrieval
quality depends on your corpus, queries, encoder and retriever; there is no
universal quality or speed lead. Evaluate settings on representative data.

## Go deeper

| Start here | Reference and project |
| :--- | :--- |
| [Installation and extras](docs/install.md) | [Classes, methods and parameters](https://oguzhankir.github.io/omnichunk/reference/chunker/) |
| [Chunking recipes](docs/usage.md) | [Source, budget and execution contracts](docs/reference/contracts.md) |
| [Indexing and integrations](docs/indexing.md) | [API stability](docs/api-stability.md) |
| [Runnable examples](examples/README.md) | [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) |

OmniChunk is currently **beta**. Before upgrading an existing index, follow the
[migration guide](docs/migrations/v2.md). The contract reference covers parser
fallbacks, overflow policies, canonical extraction, streaming memory and optional
service boundaries.

## Contributing

Bug reports, focused fixes, documentation and reproducible evaluations are
welcome. [Start with the contribution guide](CONTRIBUTING.md) for development
setup and checks.

[Report a bug](https://github.com/oguzhankir/omnichunk/issues) ·
[Security policy](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [MIT license](LICENSE)
