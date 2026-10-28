# Omnichunk examples

The Python examples use local sample data and need no API key or external service by default.
Start with the local project search for a small code and documentation example,
then the local RAG lifecycle for citations and updates and the recoverable
indexing example for durable delivery. Optional vendor recipes in `integrations/`
document their client/server requirements separately.

## Install and run

From this checkout, use the package installed in your current environment:

```bash
pip install -e .
python examples/search_local_project.py
# Install optional extras for all remaining examples:
pip install -e ".[code,semantic]"
python examples/local_rag_lifecycle.py
python examples/recoverable_indexing.py
python examples/quickstart.py
```

The base install (`pip install -e .`) runs every script except the NumPy semantic
example. The `code` extra enables AST parsing; without it, code examples use the
library's diagnosed fallbacks. Examples do not modify `sys.path` to substitute a
checkout for the installed package.

## Choose an example

### Start here

| Example | What it demonstrates |
| --- | --- |
| [quickstart.py](quickstart.py) | Chunk a document, inspect fields, and process files or batches |
| [search_local_project.py](search_local_project.py) | Search Python and documents locally with line and byte citations |

### Chunk content

| Example | What it demonstrates |
| --- | --- |
| [code_chunking.py](code_chunking.py) | Python/TypeScript, overlap, context and source reconstruction |
| [prose_and_markdown.py](prose_and_markdown.py) | Markdown structure and character or estimated-token sizes |
| [markup_chunking.py](markup_chunking.py) | JSON, YAML, TOML and HTML breadcrumbs |
| [semantic_chunking.py](semantic_chunking.py) | Semantic boundaries with a deterministic teaching encoder |
| [hierarchical_chunking.py](hierarchical_chunking.py) | Parent/child spans and retrieval granularities |
| [async_and_streaming.py](async_and_streaming.py) | Streaming, async chunking and batches |

### Build a retrieval pipeline

| Example | What it demonstrates |
| --- | --- |
| [local_rag_lifecycle.py](local_rag_lifecycle.py) | SQLite indexing, lexical retrieval, citations, edit/delete sync and reopen |
| [recoverable_indexing.py](recoverable_indexing.py) | Durable plans, replay, embedding reuse, deletion and ACL filtering |
| [incremental_diff.py](incremental_diff.py) | Stable IDs, changes and delete-before-upsert ordering |
| [token_budget_optimizer.py](token_budget_optimizer.py) | Greedy/DP selection and overlap deduplication |
| [graphrag.py](graphrag.py) | Entity–chunk graph inspection and serialization |
| [vector_db_export.py](vector_db_export.py) | Vector export dictionaries and provider identity mapping |
| [integrations/](integrations/) | Qdrant and pgvector delivery recipes and requirements |

### Extend OmniChunk

| Example | What it demonstrates |
| --- | --- |
| [plugin_api.py](plugin_api.py) | Instance-scoped parsers, formatters and diagnosed fallback |

## From a demo to an application

The lexical retriever in `local_rag_lifecycle.py` and lexical embeddings in `semantic_chunking.py` make the
examples reproducible offline. They are not production retrieval models or
quality benchmarks. Replace them with your own evaluated retriever and embedding
provider. The vector export example uses illustrative vectors only.

Examples use characters or an explicitly labelled token estimate. For a model
budget, install its matching tokenizer (for example `omnichunk[tiktoken]`) and
configure it explicitly. Count the complete prompt, including labels, separators
and instructions; a per-chunk limit does not bound the assembled prompt.

SQLite synchronization and external vector writes are separate operations. Use
the `IndexJournal` workflow in `recoverable_indexing.py` to persist pending changes and
acknowledged checkpoints. Its toy vectors illustrate lifecycle mechanics; they
are not a retrieval model. For an atomically visible cutover, build and validate
a separate retrieval generation before switching readers.
See the [indexing guide](../docs/indexing.md) and
[migration guide](../docs/migrations/v2.md) for lifecycle and recovery details.

The scripts assert source, hierarchy and lifecycle properties instead of fixed
chunk counts that vary by installed parser. CI executes the offline scripts via
`pytest tests/test_examples.py` so API changes cannot silently stale the examples.

## Search your own project

The first command above searches a tiny built-in Python and Markdown project.
To search your own files instead, run:

```bash
python examples/search_local_project.py --path /path/to/project --question "How are backups retained?"
```

The example scans `.py`, `.md` and `.txt` files and displays matching source
excerpts with line numbers and UTF-8 byte ranges. It skips hidden files and
directories, symlinks, and directories named `__pycache__`, `venv`, `env`,
`node_modules`, `build` or `dist`. Point `--path` directly at a directory if it
is intentionally named one of these.
It uses a simple in-memory lexical index; it does not call a language model or
generate an answer. Replace the retriever with an evaluated one for a production application; the
optional model step below uses these excerpts as context for an answer. Use a focused directory for large projects.

For a small, reproducible comparison of OmniChunk and fixed-size chunks, run
this existing benchmark from the repository root:

```bash
python benchmarks/run_retrieval.py --split dev --tools omnichunk,fixed --chunk-sizes 128 --unit chars --retrieval-budget 1024 --top-k 5 --repeats 1 --output /tmp/retrieval.json
```

This uses a separate synthetic development corpus and lexical retrieval, not the
project-search demo above. Its results do not establish production retrieval or
generated-answer quality. See the [benchmark guide](../benchmarks/README.md) for
the methodology, dependencies, and interpretation.

To generate an answer from the retrieved excerpts, opt in to the OpenAI API:

```bash
export OPENAI_API_KEY="your-key"
python examples/search_local_project.py --generate
# Or add --path and --question to use your own project and question.
```

This sends the question and retrieved excerpts (including source paths) to
OpenAI over the network using `gpt-4o-mini`; API usage may incur charges. Check
that you are allowed to send the selected source material before enabling it.
The key stays in your environment. Model-generated citations are not checked by
the example: compare them with the printed source excerpts before relying on an
answer. The offline default needs neither a key nor a network connection.
