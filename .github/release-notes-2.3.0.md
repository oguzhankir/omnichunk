OmniChunk 2.3.0 adds configurable chunk boundaries and improves code and document chunking, with a runnable local project search example.

## Highlights

- Optional Markdown paragraph packing and compact prose and code policies give callers additional boundary choices.
- Code and Markdown fixes improve source structure handling and bounded token-prefix processing.
- The local project search example retrieves cited excerpts offline; an explicitly enabled OpenAI API option can generate an answer from those excerpts.
- Expanded retrieval evaluations include real-source code and Turkish data, uncertainty, negative results and detailed provenance. Results vary by dataset and do not establish universal superiority.

## Install

```bash
pip install --upgrade omnichunk==2.3.0
```

The core has no mandatory external dependencies. PyPI availability follows the validated publication workflow.

## Upgrading and indexing

Default structural corrections and opt-in compact policies can change chunk boundaries and payloads. Before upgrading a production index, build and validate a separate index with the new version and configuration; update affected embeddings, switch consumers only after validation, and keep the previous index for rollback. Pin the package, configuration, tokenizer and parser versions for reproducibility. See the [migration guide](https://github.com/oguzhankir/omnichunk/blob/main/docs/migrations/v2.md) and [indexing guide](https://github.com/oguzhankir/omnichunk/blob/main/docs/indexing.md).

## Evaluation evidence

The [v3 report](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/retrieval/reports/quality-v3/README.md) documents the frozen evaluation and its limitations. Historical raw evidence is retrievable from a pinned Git snapshot with per-file hashes; it is excluded from package distributions and the current checkout. No general speed or retrieval-quality leadership is claimed.
