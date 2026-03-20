# Omnichunk examples

Runnable Python scripts that demonstrate the main APIs. **No external APIs** are required; use synthetic strings only.

## Prerequisites

```bash
pip install omnichunk
```

Token-based sizing (optional, for examples that mention tokens):

```bash
pip install omnichunk[tiktoken]
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

## Sample output (captured)

**`01_quickstart.py`** (excerpt):

```
one-shot chunk count: 2
Chunker chunk count: 2
--- first chunk ---
text (first 120 chars): 'import os\n\n'
byte_range: ByteRange(start=0, end=11)
line_range: LineRange(start=0, end=1)
breadcrumb: []
contextualized_text (first 120 chars): "# example.py\n# Language: python\n# Uses: os\n# ParseErrors: No tree-sitter parser available for 'python'\n\nimport os\n\n"
token_count: 2 char_count: 11 nws_count: 8
chunk_file count: 2
batch files: 2
  a.py: 1 chunks
  b.py: 1 chunks
```

**`06_hierarchical_chunking.py`**:

```
level_count=3
leaves=2 roots=1
at_level(1): 1 chunks
first root byte_range: ByteRange(start=0, end=93)
  children of first root: 1
parent(leaves[0]) is None? False
invariant OK: each parent byte_range spans exactly its children
to_dict: level_count=3 nodes=4
```
