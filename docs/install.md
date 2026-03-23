# Installation

```bash
pip install omnichunk
```

## Optional extras

See the [README](https://github.com/oguzhankir/omnichunk#installation) on GitHub for the full list (`tiktoken`, `formats`, `otel`, `all-languages`, etc.).

### Meta-extra `all`

Install most optional integrations **except** heavy ML stacks (e.g. `transformers`):

```bash
pip install "omnichunk[all]"
```

For HuggingFace tokenizers or transformers, install `omnichunk[transformers]` explicitly.
