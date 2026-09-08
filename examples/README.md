# Omnichunk examples

Runnable Python scripts that demonstrate the main APIs. **No external APIs** are required; use synthetic strings only.

## Prerequisites

```bash
pip install omnichunk
pip install "omnichunk[code,semantic]"  # AST and NumPy examples
```

The examples use character sizing or an explicitly labelled token estimate.
For exact model tokens, install the matching tokenizer and configure it explicitly:

```bash
pip install "omnichunk[tiktoken]"
```

From a git checkout, install in editable mode so `import omnichunk` works without `PYTHONPATH`:

```bash
pip install -e .
```

## Table of contents

| File | Topic |
|------|--------|
| `01_quickstart.py` | `chunk()`, `Chunker`, fields, `chunk_file`, `batch` |
| `02_code_chunking.py` | Python + TypeScript, overlap, `context_mode`, reconstruction |
| `03_prose_and_markdown.py` | Markdown, plaintext, `size_unit` |
| `04_markup_chunking.py` | JSON, YAML, TOML, HTML breadcrumbs |
| `05_async_and_streaming.py` | `stream`, `achunk`, `astream`, `abatch` |
| `06_hierarchical_chunking.py` | `ChunkTree`, leaves/roots/parent/children |
| `07_incremental_diff.py` | `chunk_diff`, `stable_chunk_id` |
| `08_token_budget_optimizer.py` | Greedy / DP budget, dedup |
| `09_semantic_chunking.py` | Semantic boundaries, `semantic_chunk`, topic shifts |
| `10_graphrag.py` | `build_chunk_graph`, neighbors |
| `11_vector_db_export.py` | Pinecone / Weaviate / Supabase dict shapes |
| `12_plugin_api.py` | `register_parser` / `register_formatter` |

## Run

```bash
python examples/01_quickstart.py
# … through 12
```

Output depends on installed grammars, tokenizer and documented chunking options.
The scripts assert source and hierarchy properties instead of relying on old
captured chunk counts. For persisted data, follow the
[2.x migration examples](../docs/migrations/v2.md); apply diff removals before additions.
