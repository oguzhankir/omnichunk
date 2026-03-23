# API stability

Omnichunk follows [Semantic Versioning](https://semver.org/) for **documented public APIs**.

`v0.10.1` is a **stability-focused pre-release**. The formal stable public API guarantee starts at `v1.0.0`.

## What is stable

The primary stability boundary is the **export list** in `omnichunk.__all__` (see package `__init__.py`). Symbols listed there are intended to remain compatible within the same **major** version (for `0.x`, treat **minor** bumps as the main compatibility signal).

### Version `0.x` note

While `0 < major < 1`, minor releases may add features and may include targeted breaking changes when required for correctness. Patch releases are expected to remain backward compatible for the documented public API surface.

### Version `1.x` note

Starting from `v1.0.0`, compatibility guarantees become strict for documented public symbols:

- Breaking changes require a major version bump.
- Minor versions add backward-compatible functionality.
- Patch versions contain backward-compatible fixes only.

## What is not guaranteed

Internal modules used for implementation (e.g. `omnichunk.engine.*`, many `omnichunk.util.*` helpers) may change without a major bump. Prefer importing from the top-level `omnichunk` package.

## Experimental APIs

If a feature is experimental, it will be documented as such in release notes and/or docstrings. Experimental APIs may change or move (for example under a dedicated namespace) in future releases.

## Type checking policy

CI runs `mypy` on the full `src/omnichunk` tree with the repository defaults.

For newly introduced public modules that are intended to be **strict-friendly**, CI also runs:

```bash
mypy --strict --follow-imports=skip \
  src/omnichunk/propositions/types.py \
  src/omnichunk/propositions/heuristic.py \
  src/omnichunk/propositions/llm_extract.py
```

`--follow-imports=skip` keeps this check focused on those modules without requiring the entire dependency graph to satisfy `--strict` yet.
