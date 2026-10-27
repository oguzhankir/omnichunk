# Data models

Core records are defined in `omnichunk.types` and, except for the `Language` type
alias, re-exported from `omnichunk`. They carry canonical source coordinates,
chunk payloads, context and operation results. See the [contracts](contracts.md)
for coverage, overlap, identity and final rendered-budget guarantees.

Most records below are frozen dataclasses: assigning a field raises an error,
but their contained lists and dictionaries are still mutable. Prefer
`dataclasses.replace(record, field=value)` and copied containers when changing a
record. `ChunkTree` itself is mutable. These lightweight constructors do not
calculate counters or validate every invariant; the chunking/finalization APIs
validate the records they produce.

```python
from dataclasses import replace
from omnichunk import Chunker

source = "İlk kayıt. 資料を確認する。\n"
result = Chunker(
    max_chunk_size=64, context_mode="none", coverage_policy="lossless"
).chunk_with_manifest("notes.txt", source, source_id="guide:notes")
chunk = result.chunks[0]
assert source.encode("utf-8")[chunk.byte_range.start:chunk.byte_range.end].decode("utf-8") == chunk.text
reviewed = replace(chunk, metadata={**chunk.metadata, "reviewed": True})
```

## Ranges

Coordinates refer to canonical text, including text extracted by a loader, rather
than PDF/DOCX/container bytes. Byte offsets and line numbers are zero-based.

::: omnichunk.types.ByteRange
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `start` | Inclusive offset in the canonical text encoded as UTF-8. |
| `end` | Exclusive UTF-8 offset; the interval is `[start, end)`. |

Slice encoded bytes with `source.encode("utf-8")[start:end]`; string indices are
Unicode character offsets and can differ. Constructing `ByteRange` directly does
not reject negative, reversed or out-of-source bounds.

::: omnichunk.types.LineRange
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `start` | First source line, inclusive. |
| `end` | Last source line, inclusive. |

A trailing newline is attributed to its preceding line. This inclusive line
interval differs from the half-open byte interval.

## Chunks and source identity

::: omnichunk.types.Chunk
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `text` | Exact canonical-source slice represented by the chunk. |
| `contextualized_text` | Final payload, possibly containing rendered context or line overlap; it has no source-slice guarantee. |
| `byte_range`, `line_range` | Source coordinates for `text`, not for added context. Numeric overlap can make successive byte ranges overlap. |
| `index` | Zero-based output position. Within a tree it is the position at that hierarchy level. |
| `total_chunks` | Output count for collected results; `-1` when the total is unknown during streaming. In a tree it counts chunks at that level. |
| `context` | Structured `ChunkContext`; retained even when rendered context is omitted to meet the budget. |
| `token_count` | Count of raw `text` using the chosen tokenizer; an estimate when none or `"approximate"` is selected. Default `0` on manually constructed records. |
| `char_count` | Number of Unicode characters in raw `text`; default `0`. |
| `nws_count` | Number of raw Unicode characters for which `str.isspace()` is false; default `0`. |
| `source` | Canonical-source identity/revision, or `None` for legacy/manual chunks. |
| `config_fingerprint` | Fingerprint of effective chunking configuration; default empty string for manual/legacy records. |
| `occurrence` | Zero-based source-order occurrence among byte-identical raw chunks; used to distinguish repeated content in stable IDs. Default `0`. |
| `metadata` | Additional chunk diagnostics and annotations; independent of format metadata in `context.format_metadata`. |

Counters describe raw text. Inspect `metadata["budget"]["size"]` for the final
rendered size in the configured unit and `rendered_token_count` for its token
count. Finalized chunks record the budget's `unit`, `limit`, `size`, `raw_size`,
`overflow`, `policy`, `token_accuracy` and `rendered_token_count`.
`context_omitted` and `overflow_reason` may also be present. A reported exact token
count still depends on the chosen counter matching the downstream tokenizer.

Use `stable_chunk_id(chunk)` to derive identity; `index` and byte position alone
are not stable document identities. The configuration fingerprint is also distinct
from the source revision and embedding-model revision.

::: omnichunk.types.SourceDescriptor
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `source_id` | Logical document identity. Generated text chunks default to the filepath label unless an explicit `source_id` is supplied. |
| `revision` | Generated records use the SHA-256 of the complete canonical text encoded as UTF-8. It identifies a source revision, not a chunk or model. |
| `encoding` | Encoding label, default `"utf-8"`; file APIs can retain the input decoding codec. Coordinates still refer to canonical UTF-8 text. |
| `normalization` | Transformation label: commonly `"none"`, `"extracted"`, or `"decoded:<codec>"`. Default `"none"`. |
| `format_name` | Loader/source format label, default `"text"`. |
| `metadata` | Source-level metadata, such as loader warnings; default empty dictionary. |

Preserve `source_id` across renames when the logical document remains the same.
For extracted formats, retain the canonical text and loader metadata needed to
interpret citations; the original binary container is not the coordinate space.

## Results and batches

::: omnichunk.types.ChunkResult
    options:
      heading_level: 3
      show_source: false
      members: false

Returned by `Chunker.chunk_with_manifest()`, including when retrieval output
contains no chunks.

| Field | Meaning |
| --- | --- |
| `source` | Descriptor of the complete canonical input. |
| `chunks` | Tuple of finalized chunks. |
| `skipped_ranges` | Tuple of byte intervals not covered by the union of emitted ranges; default empty. Overlap does not inflate coverage. |
| `diagnostics` | Tuple of distinct parser diagnostics collected from emitted chunks; default empty. |

An empty `chunks` tuple is not automatically a processing failure: retrieval
coverage can omit whitespace-only text. Inspect `skipped_ranges` and diagnostics.

::: omnichunk.types.BatchResult
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `filepath` | Label/path for one item in `batch()`, `abatch()` or directory processing. |
| `chunks` | Collected chunk list for that item; default empty. |
| `error` | Per-item error string, or `None` on success. |

Batch results remain in input order. Inspect `error` rather than treating an empty
chunk list as a failure: valid empty inputs can also produce no chunks.

::: omnichunk.types.UpsertBatch
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `adapter` | Serialization target: `"pinecone"`, `"weaviate"` or `"supabase"`. |
| `rows` | Adapter-shaped dictionaries ready for the caller's database client. |
| `chunks` | Tuple of source chunks corresponding to the batch; default empty. |

`Chunker.stream_upsert()` yields these records. Creating rows does not write them
to an external database or acknowledge delivery.

## Structured context

::: omnichunk.types.ChunkContext
    options:
      heading_level: 3
      show_source: false
      members: false

Context availability depends on the engine, installed parser and `context_mode`;
empty lists do not establish that the source has no relevant entities.

| Field | Default | Meaning |
| --- | --- | --- |
| `filepath` | `""` | Source filepath/label. |
| `language` | `"plaintext"` | Detected or explicitly configured language label. |
| `content_type` | `ContentType.PROSE` | Code, prose, markup or hybrid classification. |
| `scope` | `[]` | Enclosing entities, innermost first for code scope chains. |
| `breadcrumb` | `[]` | Human-readable scope names, generally outermost first. |
| `entities` | `[]` | Entities intersecting this chunk; split entities may be marked partial. |
| `siblings` | `[]` | Nearby entities before/after the chunk, when sibling context is enabled. |
| `imports` | `[]` | Extracted import dependencies retained by context options. |
| `heading_hierarchy` | `[]` | Owning headings, outermost to innermost. |
| `section_type` | `""` | Engine section label, such as `paragraph`, `table`, `code_block` or a callout label. |
| `parse_errors` | `[]` | Nonfatal parser/loader diagnostics and fallback notices. |
| `format_metadata` | `{}` | Format-specific details such as parser backend, page/cell information, front matter or callout kind. |

Format metadata and source metadata have different scopes. Context-free rendering
can still retain format/parser metadata; omitted rendered context does not erase
structured context already attached to the chunk.

::: omnichunk.types.EntityInfo
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | Required | Extracted entity name or structural label. |
| `type` | Required | `EntityType` category. |
| `signature` | `""` | Extracted signature/header text when available. |
| `docstring` | `None` | Associated documentation when extracted. |
| `byte_range`, `line_range` | `None` | Coordinates of the source entity; unavailable metadata may omit them. |
| `is_partial` | `False` | The entity extends beyond this chunk's slice. Its stored coordinates can still describe the complete entity. |
| `parent` | `None` | Name of an enclosing entity when available. |

Partial metadata does not imply missing source coverage: an oversized declaration
can span several individually budgeted chunks.

::: omnichunk.types.SiblingInfo
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Default | Meaning |
| --- | --- | --- |
| `name`, `type` | Required | Nearby entity name and `EntityType`. |
| `position` | Required | `"before"` or `"after"` the current chunk. |
| `distance` | Required | Ordinal distance among eligible neighboring entities, not bytes or lines. |
| `signature` | `""` | Optional neighboring signature. |

::: omnichunk.types.ImportInfo
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | Required | Imported name/alias extracted from the source. |
| `source` | Required | Module or package source when detectable; may be empty. |
| `is_default` | `False` | Whether the extracted import resembles a default import. |
| `is_namespace` | `False` | Whether it resembles a namespace import. |

Import extraction/filtering is heuristic metadata, not execution or full dependency
resolution.

## Hierarchy

::: omnichunk.types.ChunkNode
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `chunk` | Chunk payload at this node's level. |
| `level` | `0` for finest-grained leaves; increasing levels are coarser. |
| `parent_index` | Index in `ChunkTree.nodes`, or `None` for a root. This is not `Chunk.index`. |
| `child_indices` | Tuple of child indices in `ChunkTree.nodes`. |

::: omnichunk.types.ChunkTree
    options:
      heading_level: 3
      show_source: false
      members: [leaves, roots, at_level, parent, children, to_flat_list, to_dict]

| Constructor field | Meaning |
| --- | --- |
| `nodes` | Flat mutable list of `ChunkNode` records containing all hierarchy levels. |
| `level_count` | Number of levels; the coarsest is `level_count - 1`. |

| Method | Parameters and result |
| --- | --- |
| `leaves()` | Return level-0 chunks in source order. |
| `roots()` | Return chunks at `level_count - 1` in source order. |
| `at_level(level)` | Return chunks at integer `level`; an index outside `[0, level_count)` raises `ValueError`. |
| `parent(chunk)` | Return the parent chunk or `None`; pass the actual chunk object held by this tree. |
| `children(chunk)` | Return direct children in source order, or `[]` when none/missing; uses object identity to find `chunk`. |
| `to_flat_list(level=None)` | Return all stored chunks, or just the requested valid level. |
| `to_dict()` | Return a JSON-compatible hierarchy dictionary with node links and versioned chunk dictionaries. |

`parent()` and `children()` use object identity, so a separately deserialized or
copied but equal chunk does not resolve its relationships. Preserve `nodes` indices
when storing links. Hierarchical chunking requires non-overlapping children; see
the chunking API for level construction.

## Differences and quality summaries

::: omnichunk.types.ChunkDiff
    options:
      heading_level: 3
      show_source: false
      members: [total_updated, total_added, total_removed, total_unchanged]

| Field | Meaning |
| --- | --- |
| `added` | New chunks needing an upsert, including changed payloads with existing IDs. |
| `removed_ids` | Stable IDs to delete, including invalidated existing IDs that will be re-upserted. |
| `unchanged` | New chunk records whose stable ID and embedding fingerprint match; includes their current location metadata. |
| `updated` | Advisory subset of `added` for same-ID payload/configuration changes; default empty list. |

`total_added`, `total_removed`, `total_unchanged` and `total_updated` are the
lengths of the corresponding collections. Do not add `total_updated` to
`total_added`: updates are already included. Apply deletions before upserts.
Moving byte-identical content can preserve identity while changing location
metadata. See the [identity contract](contracts.md#identity-persistence-and-embedding-invalidation).

::: omnichunk.types.ChunkQualityScore
    options:
      heading_level: 3
      show_source: false
      members: false

Produced by `Chunker.quality_scores()` from stored raw counters and structured
metadata. These deterministic heuristics are not retrieval or answer-quality
measurements.

| Field | Meaning |
| --- | --- |
| `index` | The scored chunk's output index. |
| `overall` | Rounded weighted score: `0.45 * entity_integrity + 0.30 * scope_consistency + 0.25 * size_balance`, bounded to `[0, 1]`. |
| `entity_integrity` | Fraction of attached entities not marked partial; `1.0` when none are attached. |
| `scope_consistency` | Heuristic penalty for multiple distinct scope/parent labels. |
| `size_balance` | Preference for raw size near the midpoint of requested minimum/maximum bounds. |
| `size_value` | Stored raw token/character/NWS count used by the selected scoring unit. |

::: omnichunk.types.ChunkStats
    options:
      heading_level: 3
      show_source: false
      members: false

| Field | Meaning |
| --- | --- |
| `total_chunks` | Number of supplied chunks. |
| `average_size` | Mean stored raw size in `size_unit`, rounded to four decimals. |
| `min_size`, `max_size` | Smallest and largest stored raw sizes. |
| `size_unit` | `"tokens"`, `"chars"` or `"nws"`. |
| `entity_distribution` | Counts of attached entity occurrences keyed by `EntityType.value`; an entity appearing in multiple chunks is counted multiple times. Default empty dictionary. |

`Chunker.chunk_stats()` returns zero count/size values and an empty distribution
for an empty collection. Statistics do not remeasure rendered payloads; use each
chunk's budget metadata for that comparison.

## Configuration record

::: omnichunk.types.ChunkOptions
    options:
      heading_level: 3
      show_source: false
      show_signature: false
      members: false

`ChunkOptions` is the frozen configuration record. Prefer validated keyword
options on `Chunker`; constructing this dataclass alone does not validate them.
The [configuration contract](contracts.md#configuration-and-size) describes valid
combinations. Internal `_precomputed_*` fields are not public options.

| Field | Default | Meaning |
| --- | --- | --- |
| `max_chunk_size` | `1500` | Positive maximum for the final rendered payload in `size_unit`. |
| `min_chunk_size` | `50` | Nonnegative packing preference, no greater than the maximum; not a guaranteed lower bound. |
| `size_unit` | `"chars"` | Unicode characters, non-whitespace characters (`"nws"`) or tokenizer counts (`"tokens"`). |
| `tokenizer` | `None` | Tokenizer name or counting callable; token sizing requires an explicit choice. `"approximate"` opts into estimates. |
| `nws_backend` | `"auto"` | NWS implementation selection: `"auto"`, `"python"` or optional `"rust"`. |
| `context_mode` | `"full"` | Render full, minimal or no derived context (`"full"`, `"minimal"`, `"none"`). |
| `sibling_detail` | `"signatures"` | Neighbor context detail: `"none"`, `"names"` or `"signatures"`. |
| `max_siblings` | `3` | Maximum eligible neighbors per direction when sibling context is enabled. |
| `include_imports` | `True` | Include extracted imports in code context. |
| `filter_imports` | `False` | Apply heuristic filtering of imports for the chunk. |
| `overlap` | `None` | Nonnegative integer overlap in the selected size unit, or a fraction in `[0, 1)` of the maximum. |
| `overlap_lines` | `0` | Preceding source lines added only to rendered context; cannot combine nonzero line and numeric overlap. |
| `language` | `None` | Explicit supported `Language` label; otherwise detect it. |
| `content_type` | `None` | Explicit `ContentType` routing override; otherwise classify source. |
| `filepath` | `""` | Filepath label carried by the configuration; ordinary chunking calls supply their filepath argument. |
| `source_id` | `None` | Stable logical document identity; defaults to the filepath when absent. |
| `coverage_policy` | `"retrieval"` | Omit whitespace-only outputs; `"lossless"` retains source coverage. |
| `overflow_policy` | `"split"` | Split oversized content, reject it (`"error"`) or explicitly retain it (`"preserve"`). |
| `context_overflow` | `"omit"` | Omit derived rendered context when it cannot fit, or reject it with `"error"`. |
| `algorithm_version` | `"2.1"` | Recorded behavior-version label; currently only `"2.1"` is supported. |
| `preserve_decorators`, `preserve_comments`, `include_header_in_sections` | `True` | Compatibility settings whose only supported value is `True`. |
| `include_notebook_outputs` | `False` | Include notebook cell outputs in extracted text when enabled. |
| `semantic` | `False` | Enable embedding-based prose boundary proposals. |
| `semantic_embed_fn` | `None` | Required callback for semantic mode: `list[str]` to a finite floating two-dimensional array with one row per input and a consistent positive dimension. |
| `semantic_window` | `3` | Positive number of sentences per embedding window. |
| `semantic_threshold` | `0.3` | Finite similarity threshold in `[0, 1]` for semantic boundaries. |
| `semantic_min_sentences` | `1` | Positive minimum sentence group preference before final size enforcement. |
| `semantic_sentence_splitter` | `None` | Optional full-text to `list[str]` callback; its strings must reconstruct every source character in order. |
| `semantic_embed_cache_size` | `4096` | Per-chunker embedding LRU capacity; `0` disables caching. |
| `semantic_cache_namespace` | `None` | Stable provider/cache namespace, especially for reproducible persistent reuse. |
| `semantic_model_revision` | `""` | Caller-declared semantic model revision used in identity/caching. |
| `semantic_preprocessing` | `""` | Caller-declared semantic preprocessing identity. |
| `otel_tracer` | `None` | Optional OpenTelemetry tracer; absent disables spans. |

Unknown public-option names and internal precomputed fields are rejected by
`Chunker`. A manually created `ChunkOptions` is not a bypass for input validation.

## Enums and language labels

::: omnichunk.types.ContentType
    options:
      heading_level: 3
      show_source: false
      members: false

Use enum instances for options, for example `ContentType.CODE`, and `.value`
for serialized strings. Routing categories are:

| Member | Value | Meaning |
| --- | --- | --- |
| `CODE` | `"code"` | Source code. |
| `PROSE` | `"prose"` | Natural-language/plain or Markdown-like prose. |
| `MARKUP` | `"markup"` | Structured markup/data. |
| `HYBRID` | `"hybrid"` | Mixed content routing; emitted pieces can retain their individual content kinds. |

::: omnichunk.types.EntityType
    options:
      heading_level: 3
      show_source: false
      members: false

`EntityType` classifies extracted entities; it does not guarantee a grammar or
query extracts every listed category in every language.

| Family | Members and serialized values |
| --- | --- |
| Code declarations | `FUNCTION="function"`, `METHOD="method"`, `CLASS="class"`, `INTERFACE="interface"`, `TYPE="type"`, `ENUM="enum"`, `CONSTANT="constant"`. |
| Dependencies and modules | `IMPORT="import"`, `EXPORT="export"`, `MODULE="module"`, `MODULE_EXPORT="module_export"`, `DIRECTIVE="directive"`. |
| Other language constructs | `DECORATOR="decorator"`, `SQL_OBJECT="sql_object"`, `MACRO="macro"`, `IMPL_BLOCK="impl_block"`, `RECORD="record"`, `SEALED_INTERFACE="sealed_interface"`, `ANNOTATION="annotation"`, `PROTOCOL="protocol"`, `TYPE_ALIAS="type_alias"`. |
| Document structure | `HEADING="heading"`, `SECTION="section"`, `PARAGRAPH="paragraph"`, `LIST="list"`, `TABLE="table"`, `CODE_BLOCK="code_block"`, `FRONTMATTER="frontmatter"`. |

### Language

`Language` is a `typing.Literal` alias in `omnichunk.types`, rather than a runtime
enum or a top-level `omnichunk.Language` export. Valid labels are:

- Code: `python`, `javascript`, `typescript`, `rust`, `go`, `java`, `c`, `cpp`,
  `csharp`, `ruby`, `php`, `swift`, `kotlin`, `scala`, `haskell`, `lua`, `zig`,
  `elixir`, `sql`, `bash`.
- Prose: `plaintext`, `markdown`, `rst`.
- Markup/data: `html`, `xml`, `yaml`, `json`, `toml`.
- Structured formats: `latex`, `jupyter`, `pdf`, `docx`.

An accepted label does not establish that an optional parser is installed.
`language_capabilities()` reports parser/fallback availability.

## Errors

::: omnichunk.types.ChunkingError
    options:
      heading_level: 3
      show_source: false
      members: false

`ChunkingError` subclasses `RuntimeError`. Chunking can raise it for an invalid
source span, an impossible strict budget, explicit overflow rejection, malformed
structured input or an invalid embedding result. Parser fallback diagnostics can
instead be retained in `ChunkContext.parse_errors` without aborting the call.

Catch errors at the level appropriate to the operation: option validation also
uses `ValueError`/`TypeError`, file operations can raise `OSError` subclasses and
decoding errors, and batch APIs can capture a failure as `BatchResult.error`.
Catching only `ChunkingError` does not cover every public API failure.
