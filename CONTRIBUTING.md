# Contributing to omnichunk

Thanks for contributing.

## Quick start

1. Create a virtualenv and install dev dependencies:

```bash
pip install -e .[dev]
```

2. Run tests:

```bash
pytest -q                 # sequential, fastest for a few targeted tests
pytest -n auto -q         # parallel via pytest-xdist (CI uses this)
```

The full suite is parallel-safe. If you add a test that mutates
process-global state (env vars, singletons, module-level caches) and
cannot be isolated with `tmp_path` / `monkeypatch`, mark it with
`@pytest.mark.no_xdist` and run with `pytest -n auto -m "not no_xdist"`
plus a follow-up `pytest -m no_xdist` in series.

3. Run lint/type checks (if installed):

```bash
ruff check src tests
mypy src/omnichunk
```

## Development rules

- Keep changes deterministic.
- Preserve chunk invariants:
  - `original[chunk.byte_range.start:chunk.byte_range.end] == chunk.text`
  - ranges are contiguous, no gaps, no overlaps
  - no whitespace-only chunks
- Keep decorators/comments attached to their targets.
- Avoid unrelated refactors in bug-fix PRs.

## Pull request checklist

- [ ] Added or updated tests
- [ ] Verified local `pytest -q`
- [ ] Updated docs/README if behavior changed
- [ ] Preserved chunk invariants
- [ ] Kept rule files synchronized (`AI_RULES.md`, `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, `.github/copilot-instructions.md`)

## Commit style

Use short, descriptive commits. Prefer one concern per commit.

## Reporting issues

Please include:

- input text/file sample
- chunk options
- expected behavior vs actual behavior
- reproduction snippet
- environment (`python --version`, platform)
