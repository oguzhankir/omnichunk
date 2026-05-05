## Cursor Cloud specific instructions

This is a pure Python library with no external service dependencies. All state is in-process or file-based (SQLite via stdlib).

### Key commands

| Task | Command |
|------|---------|
| Install dev deps | `pip install -e ".[dev]"` |
| Lint | `ruff check src tests` |
| Format check | `ruff format --check src tests` |
| Type check | `mypy src/omnichunk` |
| Tests | `pytest -q` |
| Tests with coverage | `pytest -q --cov=omnichunk --cov-branch --cov-report=term-missing --cov-fail-under=90` |
| CLI demo | `omnichunk <file_or_dir> --max-size 256 --size-unit chars --stats` |

### Gotchas

- `pytest` runs with `-m 'not slow'` by default (configured in `pyproject.toml`). Slow benchmarks are skipped unless you pass `-m slow` explicitly.
- Pre-commit hooks include a `pytest -q` run and an AI rules sync check (`scripts/check_ai_rules_sync.py`). The five rule files (`AI_RULES.md`, `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, `.github/copilot-instructions.md`) must be kept identical.
- The Rust extension (`rust/omnichunk_rust/`) is optional and requires `maturin`. Core tests pass without it.
- Tree-sitter Kotlin grammar triggers a `DeprecationWarning` on `query()` — this is harmless.
