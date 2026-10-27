# Chunking options

`Chunker(**options)` sets defaults for all calls on that instance. Pass option
names again to `chunk()`, `stream()`, `chunk_file()` and other methods that accept
`**overrides` to change them for one call; the instance defaults do not change.
Top-level convenience functions such as `chunk()` accept the same options.
Unknown or internal names are rejected. Options are validated when a `Chunker`
is created and again after call overrides are applied.

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=256, context_mode="none")
small = chunker.chunk("short.txt", "Some source text.", max_chunk_size=80)
normal = chunker.chunk("other.txt", "Other source text.")  # still uses 256
```

The tables list the public fields of `ChunkOptions`. Its dataclass constructor
also exposes `_precomputed_nws_cumsum` and `_precomputed_text_index`; these are
internal and must not be passed to `Chunker`. Constructing a `ChunkOptions`
object directly does not itself perform validation. APIs that accept one, such
as `chunk_loaded_document`, validate it when used.

## Size and tokenization

| Option | Default | Accepted values and behavior |
| --- | --- | --- |
| `max_chunk_size` | `1500` | Integer ≥ 1. Maximum size of the final rendered payload in `size_unit`, except when `overflow_policy="preserve"` is selected. |
| `min_chunk_size` | `50` | Integer ≥ 0 and ≤ `max_chunk_size`. Packing preference, not a guaranteed minimum; structural boundaries and tails can produce smaller chunks. When `max_chunk_size` alone is set on construction, the default minimum is reduced to fit. A per-call maximum without a minimum similarly reduces the instance minimum if needed. |
| `size_unit` | `"chars"` | `"chars"` counts Unicode characters, `"nws"` counts non-whitespace characters, and `"tokens"` uses the configured tokenizer. |
| `tokenizer` | `None` | A nonempty tokenizer name, an object with `encode()`, or a callable returning a nonnegative integer for a string. Required for `size_unit="tokens"`. `"approximate"` explicitly selects a whitespace estimate. Named tokenizers resolve through tiktoken or locally available Hugging Face files; missing names raise an error. Encoder truncation must be disabled. Match counting and special-token handling to your downstream model. |
| `nws_backend` | `"auto"` | `"auto"`, `"python"`, or `"rust"` for non-whitespace counting. Auto uses the optional Rust extension when available and otherwise Python; an explicitly requested unavailable Rust backend raises an error when used. |
| `overflow_policy` | `"split"` | `"split"` splits oversized source spans to fit; `"error"` rejects them; `"preserve"` permits oversized units and reports overflow in chunk metadata. |
| `context_overflow` | `"omit"` | `"omit"` drops rendered context when it cannot fit, retaining structured context metadata; `"error"` rejects that situation. |

The limit applies to `chunk.contextualized_text`, including rendered context,
not only `chunk.text`. Custom counters must match the model's actual tokenization
if an exact model limit is required. See [source and budget contracts](contracts.md)
for overflow and metadata details.

```python
# pip install "omnichunk[tiktoken]"
from omnichunk import Chunker

token_chunker = Chunker(size_unit="tokens", tokenizer="cl100k_base", max_chunk_size=512)
chunks = token_chunker.chunk("guide.txt", "A short guide to chunking.")
```

## Context and overlap

| Option | Default | Accepted values and behavior |
| --- | --- | --- |
| `context_mode` | `"full"` | `"full"` includes detailed structural context; `"minimal"` uses reduced context; `"none"` disables rendered context. Available fields vary by content and parser. |
| `markdown_paragraph_policy` | `"preserve"` | `"preserve"` keeps Markdown body paragraphs as separate chunks. `"pack"` combines adjacent fitting prose paragraphs under the same heading to reduce vector count, while keeping tables, lists, fences and heading changes separate. This trades paragraph-level retrieval precision for more adjacent context and can change retrieval quality; evaluate on your data. It does not affect plaintext. |
| `prose_boundary_policy` | `"sentence"` | `"sentence"` preserves fitting sentence units during oversized prose fallback. `"compact"` also tries a clause/word partition and uses it when it has equal or fewer fragments. Compact mode can cut a sentence that would fit by itself and trades semantic isolation for fuller payloads; source and budget contracts remain enforced. It applies to oversized prose, not AST code units or fitting paragraphs. |
| `code_boundary_policy` | `"structure"` | `"structure"` follows AST boundaries. `"compact"` compares measured layouts for oversized code and chooses fewer fragments, then more balanced payload sizes. It may divide expressions inside oversized declarations while retaining fitting definitions and documented root groups. Applies only with `overflow_policy="split"`; evaluate its retrieval tradeoffs on your corpus. |
| `sibling_detail` | `"signatures"` | `"none"`, `"names"`, or `"signatures"`. Controls nearby code sibling information in full context. |
| `max_siblings` | `3` | Integer ≥ 0. Maximum number of nearby code siblings included when sibling details are enabled. |
| `include_imports` | `True` | Boolean. Include detected code imports in context when available. |
| `filter_imports` | `False` | Boolean. Filter detected imports using signatures of entities in a code chunk; has no effect when imports are disabled. |
| `overlap` | `None` | Nonnegative integer smaller than `max_chunk_size`, measured in `size_unit`, or a finite float in `[0, 1)` representing a fraction of the maximum. Repeats source spans; actual overlap may be smaller to satisfy the budget. |
| `overlap_lines` | `0` | Integer ≥ 0. Adds preceding lines to derived context, not the raw chunk range. Requires context and cannot be combined with nonzero `overlap`. |

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=200, overlap=20, context_mode="none")
chunks = chunker.chunk("notes.txt", "A long note. " * 100)
```

## Source, format and preservation

| Option | Default | Accepted values and behavior |
| --- | --- | --- |
| `language` | `None` | One of the language names below, or `None` to detect from the file/content. Overrides detection; parser availability depends on installed extras. |
| `content_type` | `None` | A `ContentType` enum member (`CODE`, `PROSE`, `MARKUP`, or `HYBRID`), or `None` for detection. Pass the enum, not its string value. |
| `filepath` | `""` | String source label used by APIs taking `ChunkOptions` directly. `Chunker` methods that take a filepath use that argument for the call. |
| `source_id` | `None` | Nonempty string identifying the logical source, or `None` to use the filepath. Keep it stable across renames when identity must persist. |
| `coverage_policy` | `"retrieval"` | `"retrieval"` may omit whitespace-only ranges; `"lossless"` retains the source coverage. With overlap, reconstruct using the union of ranges rather than concatenation. |
| `algorithm_version` | `"2.1"` | Only `"2.1"` is supported; recorded in the configuration for reproducibility. |
| `preserve_decorators` | `True` | Boolean compatibility option. Only `True` is supported. |
| `preserve_comments` | `True` | Boolean compatibility option. Only `True` is supported. |
| `include_header_in_sections` | `True` | Boolean compatibility option. Only `True` is supported. |
| `include_notebook_outputs` | `False` | Boolean. Include notebook cell outputs in extracted canonical text when loading a notebook; by default outputs are excluded. |

Supported `language` values: `python`, `javascript`, `typescript`, `rust`, `go`,
`java`, `c`, `cpp`, `csharp`, `ruby`, `php`, `swift`, `kotlin`, `scala`,
`haskell`, `lua`, `zig`, `elixir`, `sql`, `bash`, `rst`, `markdown`, `html`,
`xml`, `yaml`, `json`, `toml`, `plaintext`, `latex`, `jupyter`, `pdf`, `docx`.
Use `language_capabilities()` to inspect installed code-parser support.

```python
from omnichunk import Chunker, ContentType

chunker = Chunker(coverage_policy="lossless", context_mode="none")
result = chunker.chunk_with_manifest(
    "note.txt", "First paragraph.\n\nSecond paragraph.\n",
    source_id="notes:42", content_type=ContentType.PROSE,
)
assert not result.skipped_ranges
```

## Semantic splitting

Semantic mode needs the `semantic` extra and an embedding provider. It proposes
boundaries for prose from adjacent sentence-window similarities; the normal
size and source contracts still apply. A size limit can force additional splits.

| Option | Default | Accepted values and behavior |
| --- | --- | --- |
| `semantic` | `False` | Boolean. Enable embedding-based semantic splitting. Requires a callable `semantic_embed_fn`. |
| `semantic_embed_fn` | `None` | Callable taking `list[str]` and returning finite floating embeddings of shape `(N, D)`, one row per input, with consistent positive dimension. The application supplies and owns the model. |
| `semantic_window` | `3` | Integer ≥ 1. Number of nearby sentences used to build each embedding window. |
| `semantic_threshold` | `0.3` | Finite number in `[0, 1]`. Adjacent window similarity below this threshold is a candidate boundary; local similarity valleys can also be boundaries. |
| `semantic_min_sentences` | `1` | Integer ≥ 1. Minimum sentences on each side of a proposed semantic boundary; final budget splitting can still produce smaller chunks. |
| `semantic_sentence_splitter` | `None` | Optional callable accepting a string and returning a list of sentence strings that concatenate exactly to the input, including whitespace. `None` uses the built-in heuristic. |
| `semantic_embed_cache_size` | `4096` | Integer ≥ 0. Per-`Chunker` embedding-cache capacity; `0` disables caching. |
| `semantic_cache_namespace` | `None` | String or `None`. Identifies the cache/provider namespace; for persisted skip decisions provide both a stable namespace and a model revision, or a stable callback fingerprint. |
| `semantic_model_revision` | `""` | String identifying the embedding model revision for cache and configuration identity. Change it when the model changes. |
| `semantic_preprocessing` | `""` | String identifying preprocessing for cache and configuration identity. Change it when preprocessing changes. |

```python
# pip install "omnichunk[semantic]"
import numpy as np
from omnichunk import Chunker

def embed(texts: list[str]) -> np.ndarray:
    # Replace this deterministic toy function with your embedding model.
    return np.array([[len(text), text.count(" ") + 1] for text in texts], dtype=float)

chunker = Chunker(semantic=True, semantic_embed_fn=embed, semantic_window=3)
chunks = chunker.chunk("article.txt", "First sentence. Second sentence. Third sentence.")
```

## Tracing

| Option | Default | Accepted values and behavior |
| --- | --- | --- |
| `otel_tracer` | `None` | Optional OpenTelemetry tracer object used for spans; `None` disables tracing. Install the `otel` extra when integrating OpenTelemetry. |
