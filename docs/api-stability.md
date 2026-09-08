# API stability

Omnichunk uses semantic versioning for documented public APIs. The working tree
implements the major 2.0 contract transition and additive 2.1 code-quality work;
implementation and package publication are separate milestones. Package metadata,
runtime `__version__` and CLI output use `src/omnichunk/_version.py` as their single
version source. Release checks compare the selected tag with built artifacts.

## Compatibility boundary

The public surface includes documented exports in `omnichunk.__all__`, their
methods, and explicitly documented APIs such as `omnichunk.store.migrate_legacy_store`.
Internal engine/windowing/util helpers are not stable extension points. Prefer
the public `Chunker`, loader and registry APIs.

Within 2.x, minor versions add compatible functionality and patch versions fix
compatible behavior. The major transition changes default sizing, validation,
source/budget contracts, identity, dependency extras and persistence schemas.
The [migration guide](migrations/v2.md) documents actual replacements, index
rebuilding and rollback; the [roadmap](https://github.com/oguzhankir/omnichunk/blob/main/ROADMAP.md)
tracks future additions and any announced removals for 3.0.

`algorithm_version="2.1"` records the current chunking behavior; it does not provide
an implementation of older algorithms. Reproducible output assumes the same source,
options, parser/tokenizer versions and callback results. Keep the old package
runtime when reproducing a previous index generation.

Persisted chunk JSON has an explicit schema version and reads legacy records.
SQLite schema migration requires a separate destination and preserves its source.
Schema readability does not make old boundaries or embeddings equivalent to the
new output. IDs and embedding invalidation have separate contracts.

## Source and execution behavior

The [contracts reference](reference/contracts.md) defines final payload budgets,
UTF-8 byte coordinates, canonical extracted sources, coverage modes, overlap,
iterator parity, identity and synchronization. `contextualized_text` is derived
text; `Chunk.text` is the verifiable source slice.

Iterator APIs retain document text and parser state. Async queue backpressure
bounds queued output, not total process memory. External callbacks can introduce
latency or nondeterminism and cannot be forcibly cancelled by Python wrappers.

The experimental `serve --rpc` service uses custom JSON-RPC. Its deprecated
`--mcp` alias does not implement MCP initialization or standard tool discovery.
This explicit experimental boundary does not retroactively classify other
established public APIs as experimental.

## Type checking

CI checks the full package with strict mypy and ships the PEP 561 `py.typed` marker:

```bash
mypy --strict src/omnichunk
```

Behavioral and property tests separately validate source fidelity, budget limits
and persistence safety; types alone do not prove those properties.
