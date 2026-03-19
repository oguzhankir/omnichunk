# omnichunk

Chunk code, prose, and markup files with structure awareness.

`omnichunk` is a Python library that splits files into smaller pieces while keeping useful context:

- **Code**: respects function/class boundaries, includes scope and import information
- **Markdown**: respects headings and sections
- **JSON/YAML/TOML**: splits by top-level keys/sections
- **HTML/XML**: splits by elements
- **Mixed files**: handles notebooks and Python files with long docstrings

Each chunk includes:
- The original text slice
- Byte and line ranges for lossless reconstruction
- Context (scope, entities, headings, imports, siblings)
- Optional `contextualized_text` for embeddings

The library is deterministic and works without external APIs.

## Installation

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e .[dev]
pip install -e .[all-languages]
pip install -e .[tiktoken]
pip install -e .[transformers]
```

## Quick start

### One-shot API

```python
from omnichunk import chunk

code = """
import os

def hello(name: str) -> str:
    return f"hello {name}"
"""

chunks = chunk("example.py", code, max_chunk_size=128, size_unit="chars")

for c in chunks:
    print(c.index, c.byte_range, c.context.breadcrumb)
    print(c.contextualized_text)
```

### Reusable `Chunker`

```python
from omnichunk import Chunker

chunker = Chunker(
    max_chunk_size=1024,
    min_chunk_size=80,
    tokenizer="cl100k_base",
    context_mode="full",
    overlap=0.1,
    overlap_lines=1,
)

chunks = chunker.chunk("api.py", source_code)

for c in chunker.stream("large.py", large_source):
    consume(c)

batch_results = chunker.batch(
    [
        {"filepath": "a.py", "code": code_a},
        {"filepath": "b.ts", "code": code_b},
        {"filepath": "README.md", "code": readme_md},
    ],
    concurrency=8,
)
```

### File API

```python
from omnichunk import chunk_file

chunks = chunk_file("path/to/file.py")
```

## Chunk model

Every `Chunk` includes raw content, exact offsets, and rich context:

- `text`: exact source slice (lossless reconstruction)
- `contextualized_text`: embedding-ready representation
- `byte_range`, `line_range`
- `context`: scope, entities, siblings, imports, headings, section metadata
- `token_count`, `char_count`, `nws_count`

## Supported content

### Code

- Python
- JavaScript / TypeScript
- Rust
- Go
- Java
- C / C++ / C#
- Ruby / PHP / Kotlin / Swift (grammar-dependent)

### Prose

- Markdown
- Plaintext

### Markup

- JSON
- YAML
- TOML
- HTML / XML

### Hybrid

- Python with heavy docstrings
- Notebook-style `# %%` cell files

## Architecture

```
src/omnichunk/
├── chunker.py
├── types.py
├── engine/
│   ├── router.py
│   ├── code_engine.py
│   ├── prose_engine.py
│   ├── markup_engine.py
│   └── hybrid_engine.py
├── parser/
│   ├── tree_sitter.py
│   ├── markdown_parser.py
│   ├── html_parser.py
│   └── languages.py
├── context/
│   ├── entities.py
│   ├── scope.py
│   ├── siblings.py
│   ├── imports.py
│   └── format.py
├── sizing/
│   ├── nws.py
│   ├── tokenizers.py
│   └── counter.py
└── windowing/
    ├── greedy.py
    ├── merge.py
    ├── split.py
    └── overlap.py
```

## Determinism & integrity guarantees

`omnichunk` is built to preserve source fidelity:

- Chunk boundaries are deterministic
- Empty/whitespace-only chunks are dropped
- Chunks are contiguous and non-overlapping in source order
- Byte range integrity is validated in tests:

```python
original_bytes = source.encode("utf-8")
for chunk in chunks:
    assert original_bytes[chunk.byte_range.start:chunk.byte_range.end].decode("utf-8") == chunk.text
```

## Testing

Run the test suite:

```bash
pytest -q
```

Current suite covers:

- API usage (`chunk`, `chunk_file`, `Chunker`)
- Code/prose/markup/hybrid behavior
- Context metadata (imports, siblings, scope, headings)
- Sizing/tokenization/NWS logic
- Overlap behavior
- Edge cases (empty input, unicode, malformed syntax, range contiguity)

## Notes

- Tree-sitter grammars are resolved dynamically and cached per language.
- If a parser is unavailable, the system degrades gracefully with fallback heuristics.
- `contextualized_text` is optimized for embedding quality while preserving raw `text` separately.