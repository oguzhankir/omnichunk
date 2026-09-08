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
| `langchain`, `llamaindex` | Framework document conversion. |
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
