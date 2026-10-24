# Omnichunk examples

Runnable workflows using local sample data. No API key or external service is
required. Start with the local RAG lifecycle to see how chunks, citations, updates
and deletions work together.

## Install and run

From this checkout, use the package installed in your current environment:

```bash
pip install -e ".[code,semantic]"
python examples/13_local_rag_lifecycle.py
python examples/01_quickstart.py
```

The base install (`pip install -e .`) runs every script except the NumPy semantic
example. The `code` extra enables AST parsing; without it, code examples use the
library's diagnosed fallbacks. Examples do not modify `sys.path` to substitute a
checkout for the installed package.

| File | What it demonstrates |
| --- | --- |
| [13_local_rag_lifecycle.py](13_local_rag_lifecycle.py) | SQLite indexing, lexical retrieval, exact citations, edit/delete sync, repeat skips and reopen |
| [01_quickstart.py](01_quickstart.py) | `chunk()`, `Chunker`, fields, files and batches |
| [02_code_chunking.py](02_code_chunking.py) | Python/TypeScript, overlap, context and source reconstruction |
| [03_prose_and_markdown.py](03_prose_and_markdown.py) | Markdown structure and explicit character/token-estimate sizing |
| [04_markup_chunking.py](04_markup_chunking.py) | JSON, YAML, TOML and HTML breadcrumbs |
| [05_async_and_streaming.py](05_async_and_streaming.py) | Iteration, async chunking and batches |
| [06_hierarchical_chunking.py](06_hierarchical_chunking.py) | Parent/child spans and retrieval granularities |
| [07_incremental_diff.py](07_incremental_diff.py) | Stable IDs, changes and delete-before-upsert ordering |
| [08_token_budget_optimizer.py](08_token_budget_optimizer.py) | Greedy/DP selection and overlap deduplication |
| [09_semantic_chunking.py](09_semantic_chunking.py) | Semantic callback mechanics with a deterministic lexical teaching encoder |
| [10_graphrag.py](10_graphrag.py) | Entity–chunk graph inspection and serialization |
| [11_vector_db_export.py](11_vector_db_export.py) | Vector export dictionaries and provider identity mapping |
| [12_plugin_api.py](12_plugin_api.py) | Instance-scoped parsers, formatters and diagnosed fallback |

Optional notebooks in [notebooks/](notebooks/) explore hierarchy and semantic
boundaries. The semantic notebook uses Matplotlib when installed and otherwise
prints its curve data; notebook execution also requires a notebook frontend.

## From a demo to an application

The lexical retriever in example 13 and lexical embeddings in example 09 make the
examples reproducible offline. They are not production retrieval models or
quality benchmarks. Replace them with your own evaluated retriever and embedding
provider. The vector export example uses illustrative vectors only.

Examples use characters or an explicitly labelled token estimate. For a model
budget, install its matching tokenizer (for example `omnichunk[tiktoken]`) and
configure it explicitly. Count the complete prompt, including labels, separators
and instructions; a per-chunk limit does not bound the assembled prompt.

SQLite synchronization and external vector writes are separate operations. The
local example's in-memory projection is not a durable delivery queue. Persist a
replayable plan or build and validate a new retrieval generation before cutover.
See the [indexing guide](../docs/indexing.md) and
[migration guide](../docs/migrations/v2.md) for lifecycle and recovery details.

The scripts assert source, hierarchy and lifecycle properties instead of fixed
chunk counts that vary by installed parser. CI executes the numbered scripts via
`pytest tests/test_examples.py` so API changes cannot silently stale the examples.
