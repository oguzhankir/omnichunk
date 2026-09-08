<div align="center">
  <img src="https://raw.githubusercontent.com/oguzhankir/omnichunk/main/assets/omnichunk-logo.png" alt="omnichunk" width="360">
  <br><br>
  <a href="https://pypi.org/project/omnichunk/"><img src="https://img.shields.io/pypi/v/omnichunk?v=3" alt="PyPI"></a>
  <a href="https://github.com/oguzhankir/omnichunk/actions/workflows/ci.yml"><img src="https://github.com/oguzhankir/omnichunk/actions/workflows/ci.yml/badge.svg?v=3" alt="CI"></a>
  <a href="https://codecov.io/gh/oguzhankir/omnichunk"><img src="https://codecov.io/gh/oguzhankir/omnichunk/branch/main/graph/badge.svg?precision=2" alt="Codecov (Cobertura includes branch data from pytest --cov-branch)"></a>
  <a href="https://pypi.org/project/omnichunk/"><img src="https://img.shields.io/pypi/pyversions/omnichunk?v=3" alt="Python"></a>
  <a href="https://github.com/oguzhankir/omnichunk/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/omnichunk?v=3" alt="License"></a>
</div>

# Omnichunk

Structure-aware chunking for code, prose and mixed documents. Chunks carry source
ranges and context such as scopes, imports, headings and notebook cells, with
helpers for indexing and retrieval workflows.

**Development status:** Omnichunk’s 2.0 foundation work and the 2.1 milestone
were implemented in **v2.1.0**, and the latest maintenance line is tracked from
there through **2.1.2**. Read the
[migration guide](docs/migrations/v2.md) before upgrading existing indexes.
The [roadmap](ROADMAP.md) tracks verification, compatible additions through 3.0,
and the 4.0 vision.

[Documentation](https://oguzhankir.github.io/omnichunk/) ·
[Architecture](ARCHITECTURE.md) · [Examples](examples/README.md) ·
[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Installation

Python 3.10 or newer:

```bash
pip install omnichunk
pip install "omnichunk[code]"           # six primary Tree-sitter grammars
pip install "omnichunk[tiktoken]"       # named OpenAI tokenizers
pip install "omnichunk[all-languages]"  # additional Tree-sitter grammars
pip install "omnichunk[formats]"        # PDF and DOCX text extraction
```

The base package has no mandatory third-party dependencies. Install `code` for
AST parsing and `semantic` for NumPy-based semantic utilities. Without a grammar,
code uses a diagnosed fallback. Structural chunking requires no external service;
optional model/tokenizer integrations may download assets or use your callbacks.

Other extras include `transformers`, `sentence-transformers`, `scipy`, `langchain`,
`llamaindex`, `otel`, `docs`, `dev` and optional Rust build tooling (`rust`).
See [installation details](docs/install.md) for the full grouping and limitations.

## Quick start

```python
from omnichunk import Chunker

source = 'import os\n\ndef hello(name: str) -> str:\n    return f"hello {name}"\n'
chunker = Chunker(max_chunk_size=256, size_unit="chars")
chunks = chunker.chunk("example.py", source)

for item in chunks:
    print(item.byte_range, item.context.breadcrumb)
    print(item.contextualized_text)
```

For token sizing, configure the tokenizer explicitly after installing its extra:

```python
chunker = Chunker(
    max_chunk_size=512,
    size_unit="tokens",
    tokenizer="cl100k_base",
    context_mode="full",
)
```

Every public chunking path validates the final rendered payload. The default
`overflow_policy="split"` enforces the selected budget; `"error"` rejects oversized
units and `"preserve"` explicitly reports structural overflow in metadata.
Context that will not fit is omitted by default, or rejected with
`context_overflow="error"`. Token mode requires an explicit tokenizer/counter;
`tokenizer="approximate"` is available as a clearly labelled estimate.

## Implemented capabilities

- **Code structure:** Tree-sitter boundaries, declarations, scope, sibling/import
  context and structural splitting. The `code` extra covers Python, JavaScript,
  TypeScript, Rust, Go and Java. Optional grammars cover C/C++/C#, Ruby, PHP, Kotlin,
  Swift, SQL, Bash, Scala and Elixir; extraction depth depends on the grammar.
- **Prose and mixed documents:** Markdown headings/lists/tables, delegated fenced
  code and markup, plaintext, JSON/YAML/TOML, HTML/XML and hybrid Python cells.
  Loaders also handle RST, notebooks, LaTeX and optional PDF/DOCX text extraction.
- **Semantic utilities:** caller-supplied embeddings, adaptive boundary detection,
  embedding cache/validation, local embedding helper, topic shifts, dense/sparse
  TF-IDF and MMR reranking. Structural engines still handle non-prose routing.
- **Retrieval utilities:** hierarchical chunk trees, incremental diffs, SQLite
  storage, token-budget selection, exact/near deduplication, entity–chunk graphs,
  centrality/community analysis and heuristic/callback-based propositions.
- **Integration:** synchronous/async/batch APIs, iterators, CLI, JSONL/CSV,
  LangChain/LlamaIndex document conversion, vendor-shaped vector payloads,
  parser/formatter registration and optional OpenTelemetry.

Use `language_capabilities()` to distinguish detected languages, installed
grammars, extraction queries and fallback behavior. The
[contract reference](docs/reference/contracts.md) defines guarantees and limits.
Graph helpers provide entity relationships; they are not a complete GraphRAG
retriever. PDF/DOCX support extracts text; it does not provide OCR or full layout.

## Files, directories and CLI

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=512, size_unit="chars")
chunks = chunker.chunk_file("README.md")
results = chunker.chunk_directory("./src", glob="**/*.py", concurrency=4)

for result in results:
    if result.error:
        print(result.filepath, result.error)
    else:
        print(result.filepath, len(result.chunks))
```

Pass binary PDF/DOCX paths to `chunk_file()` rather than reading them as strings.

```bash
omnichunk ./src --glob "**/*.py" --max-size 512 --size-unit chars --format jsonl > chunks.jsonl
omnichunk README.md --max-size 256 --size-unit chars --stats
omnichunk README.md --format csv --output chunks.csv
omnichunk eval chunks.jsonl --metrics all
```

For reconstruction evaluation, `--source` must name the same canonical source
that produced the chunks; combining unrelated files with one source is invalid.
Current offline coherence/coverage metrics are heuristics, not retrieval scores.

## Source ranges and context

Each `Chunk` contains `text`, `contextualized_text`, `byte_range`, `line_range`,
context metadata and size counts. Byte ranges are zero-based, half-open UTF-8
intervals. Line ranges are zero-based and inclusive. For ordinary text:

```python
chunks = chunker.chunk("example.py", source)
raw = source.encode("utf-8")
for item in chunks:
    assert raw[item.byte_range.start:item.byte_range.end].decode("utf-8") == item.text
```

Use chunks from the same `source` in this check. Structured loaders return ranges
in their canonical `LoadedDocument.text`, which may differ from notebook JSON or
original PDF/DOCX bytes. `contextualized_text` adds derived context and is not an
exact source slice. Default `coverage_policy="retrieval"` may omit trivia;
`chunk_with_manifest()` reports skipped byte ranges for canonical text.
`coverage_policy="lossless"` covers every canonical byte, including whitespace-only
input. With overlap disabled, concatenating lossless chunks reconstructs the
source. Each chunk records its logical source ID, revision and configuration
fingerprint. See the [source contract](docs/reference/contracts.md).

## Async, iterators and exports

```python
import asyncio
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=256, size_unit="chars")
chunks = asyncio.run(chunker.achunk("example.py", source))

for item in chunker.stream("example.py", source):
    print(item.text)
```

Iterators accept a complete source string and retain source/AST state. `stream()`
and `chunk()` share boundaries, overlap and budget policies; streaming reports
`total_chunks=-1`. `astream(buffer_size=8)` bounds queued output and supports
cooperative cancellation. `stream_upsert()` keeps a bounded export batch and
streams ordinary-file chunks; structured extraction and semantic analysis still
retain per-document state. It produces rows for your database client.

Vector helpers produce plain data structures; compute embeddings and use the
vendor's client separately. JSONL/CSV and framework conversions are available on
`Chunker`; runnable demonstrations live in [examples](examples/README.md).

## Indexing and compatibility

Content/occurrence IDs and separate embedding fingerprints detect edits and
context/configuration changes. `ChunkStore` scopes data to named collections,
updates atomically and preserves last good state after failures. Apply diff
removals before additions; `updated` is an advisory subset of `added`.
Versioned JSON round-trips full chunk metadata. The
[migration guide](docs/migrations/v2.md) includes legacy conversion and separate
index rebuild/rollback examples.

Semantic caches isolate provider, model revision and preprocessing. Give opaque
callbacks an explicit stable fingerprint/revision for durable reuse. Parser and
formatter plugins can be scoped through `PluginRegistry`.

`omnichunk serve --rpc` exposes custom HTTP JSON-RPC with a resolved allowed root,
Host/Origin checks, request limits and loopback defaults. Non-loopback binding
requires authentication. The deprecated `--mcp` alias retains that RPC behavior;
standard MCP lifecycle support remains a later optional integration.

## Development and evaluation

```bash
pip install -e ".[dev,docs]"
pytest -q
ruff check src tests
ruff format --check src tests
mypy src/omnichunk
python scripts/check_ai_rules_sync.py
python scripts/check_benchmarks.py --run-quality
mkdocs build --strict
```

Default pytest includes bounded Hypothesis source invariants and excludes only
tests marked `slow`. Coverage measures all Python source with a 90% aggregate
line-and-branch gate. The [roadmap](ROADMAP.md) separates local verification from
the release matrix and publication checks.

[Benchmark instructions](benchmarks/README.md) explain reproducibility and the
current comparison limitations. No universal speed or retrieval-quality leadership
claim has been established.

Maintainer and project process are consolidated in [CONTRIBUTING.md](CONTRIBUTING.md).
See also the [security policy](SECURITY.md) and [code of conduct](CODE_OF_CONDUCT.md).
