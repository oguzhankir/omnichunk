# Installation

Python 3.10 or newer is required. These instructions describe the implementation
prepared for the 2.0 / 2.1 transition; use the published package version appropriate
to your deployment, or install this checkout to test unreleased changes.

```bash
pip install omnichunk
# For this checkout:
pip install -e ".[dev,docs]"
```

The base package has no mandatory third-party dependencies. Plain-text/markup
chunking and deterministic code fallbacks work without NumPy or Tree-sitter.
Install code grammars for AST boundaries and richer entity extraction:

```bash
pip install "omnichunk[code]"
pip install "omnichunk[all-languages,formats]"
```

| Extra | Dependencies or capability |
| --- | --- |
| `code` | Tree-sitter and Python, JavaScript, TypeScript, Rust, Go and Java grammars. |
| `all-languages` | `code` dependencies plus the registered C/C++/C#, Ruby, PHP, Kotlin, Swift, SQL, Bash, Scala and Elixir grammars. |
| `semantic` | NumPy for semantic helpers; supply an embedding callback. |
| `tiktoken` | Named tiktoken counters, such as `tokenizer="cl100k_base"`. |
| `transformers` | Hugging Face tokenizer support. |
| `sentence-transformers` | Optional local embedding-model helper. |
| `scipy` | Sparse TF-IDF support. |
| `pdf`, `docx`, `formats` | PDF reader, DOCX reader, or both. |
| `langchain`, `llamaindex` | Native splitter/node-parser adapters and document conversion. |
| `qdrant` | Qdrant client for acknowledged local/server vector delivery. |
| `pgvector` | Psycopg PostgreSQL client; the server needs the pgvector extension. |
| `otel` | OpenTelemetry API. |
| `profiling` | py-spy and line-profiler. |
| `rust` | Maturin build tooling; not a prebuilt accelerator. |
| `docs`, `dev` | Documentation and development tooling. |

`all` combines code/extended grammars, NumPy, formats, tiktoken, tracing, framework
conversions and profiling. It excludes the heavier Transformers,
sentence-transformers and SciPy extras, Rust tooling, and docs/dev tools.

`graph`, `pinecone`, `weaviate`, `supabase`, `vectordb` and `mcp` are empty marker
extras. Vector exports return dictionaries without vendor clients. The `mcp`
marker does not implement MCP protocol support; the experimental server uses
stdlib HTTP JSON-RPC.

A tokenizer or model may need its own vocabulary/model files. Prepare those assets
for offline environments; installation alone does not guarantee they are cached.
See [contracts](reference/contracts.md) for exact token sizing and language
capability reporting, and [migration](migrations/v2.md) before replacing an index.

## Native integration compatibility

The optional integration workflow exercises both declared minimum versions and
the latest compatible releases. The initial M2 validation used:

| Integration | Minimum tested | Current tested | Supported constraint |
| --- | --- | --- | --- |
| LangChain core / splitters | 0.2.11 / 0.2.2 | 1.7.0 / 1.1.3 | core `<2`, splitters `<2` |
| LlamaIndex core | 0.10.68.post1 | 0.14.25 | `>=0.10.68.post1,<0.15` |
| Qdrant client | 1.12.0 | 1.20.0 | `>=1.12,<2` |
| Psycopg binary | 3.2.1 | 3.3.6 | `>=3.2.1,<4` |

Framework and sink compatibility is checked on Python 3.12; the ordinary library
matrix covers Python 3.10–3.13. Qdrant tests use its real local client. PostgreSQL
tests use a disposable PostgreSQL 16 server with pgvector; production servers and
credentials remain application-owned. See [indexing](indexing.md) for native
adapter examples, delivery semantics and remote provisioning.
