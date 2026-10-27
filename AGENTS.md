# Repository instructions

This is a pure Python library with no external service dependencies. All state is in-process or file-based (SQLite via stdlib).

### Documentation requirements

- When a change affects documented behavior or how users install, configure, or use the library, update the relevant documentation in the same change. This includes public classes, functions, parameters, defaults, accepted values, return types, CLI commands, integrations, and compatibility or migration guidance.
- Keep API references, usage examples, and configuration guidance consistent with the implementation. Add documentation for new public functionality and revise or remove stale guidance when behavior changes.
- Run `mkdocs build --strict` for documentation changes and verify affected examples where practical.

### Key commands

| Task | Command |
|------|---------|
| Install dev deps | `pip install -e ".[dev,docs,langchain,llamaindex]"` |
| Lint | `ruff check src tests` |
| Format check | `ruff format --check src tests` |
| Type check (Python 3.12 environment) | `mypy --python-version 3.12 src/omnichunk` |
| Tests | `pytest -q` |
| Tests with coverage | `pytest -q --cov=omnichunk --cov-branch --cov-report=term-missing --cov-fail-under=90` |
| Documentation | `mkdocs build --strict` |
| Quality gate | `python scripts/check_benchmarks.py --run-quality` |
| CLI demo | `omnichunk <file_or_dir> --max-size 256 --size-unit chars --stats` |

### Gotchas

- `pytest` runs with `-m 'not slow'` by default (configured in `pyproject.toml`). Slow benchmarks are skipped unless you pass `-m slow` explicitly.
- This file is the single source of repository instructions for coding agents. Keep product documentation in the MkDocs site and planning in `ROADMAP.md`.
- Pre-commit hooks run Ruff, mypy and `pytest -q`.
- Match mypy's `--python-version` to the installed interpreter when optional dependency stubs use newer syntax; CI checks every supported Python version.
- The Rust extension (`rust/omnichunk_rust/`) is optional and requires `maturin`. Core tests pass without it.
- Tree-sitter Kotlin grammar triggers a `DeprecationWarning` on `query()` — this is harmless.
