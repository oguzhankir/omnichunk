# Contributing to omnichunk

Thanks for contributing.

## Quick start

1. Create a virtualenv and install dev dependencies:

```bash
pip install -e ".[dev]"
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

3. Run lint, formatting, and type checks:

```bash
ruff check src tests
ruff format --check src tests
mypy src/omnichunk
```

## Development rules

- Keep changes deterministic.
- Preserve chunk invariants:
  - byte ranges identify exact UTF-8 source slices, as shown below
  - lossless mode covers all canonical bytes; retrieval mode may omit trivia
  - numeric overlap is explicit and final rendered payloads obey the chosen budget policy
  - retrieval mode drops whitespace-only chunks; lossless mode retains them
- Keep decorators/comments attached to their targets.
- Avoid unrelated refactors in bug-fix PRs.

Validate byte ranges against encoded text, not Python character indices:

```python
source_bytes = source.encode("utf-8")
for chunk in chunks:
    start, end = chunk.byte_range.start, chunk.byte_range.end
    assert source_bytes[start:end].decode("utf-8") == chunk.text
```

For structured document loaders, `source` in this check is the canonical
`LoadedDocument.text`. Extracted PDF/DOCX text and notebook cell text do not
reconstruct the original binary container or notebook JSON.

## Pull request checklist

- [ ] Added or updated tests
- [ ] Verified local `pytest -q`
- [ ] Verified lint, formatting, and type checks
- [ ] Updated docs/README if behavior changed
- [ ] Preserved chunk invariants
- [ ] Kept rule files synchronized (`AI_RULES.md`, `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, `.github/copilot-instructions.md`)

## Commit style

Use short, descriptive commits. Prefer one concern per commit.

## Maintainers and governance

The current maintainer is [@oguzhankir](https://github.com/oguzhankir).
Maintainers review pull requests and issues, keep CI healthy, and maintain
release quality and roadmap priorities.

### Decision process

- Small changes require maintainer review and merge.
- Larger API or behavior changes require a design note in the pull request
  description and at least one maintainer approval.
- Breaking changes require migration notes in the README/changelog.

### Release process

- Releases are cut from `main` after tests pass.
- Versioning follows Semantic Versioning.
- Set the version only in `src/omnichunk/_version.py`; Hatch derives package
  metadata from it. The release tag must match that version.
- Run the full line-and-branch coverage gate (90%, no core exclusions), strict
  MkDocs build, rule sync and benchmark checks. Validate the built wheel/sdist
  with `python scripts/check_release.py --help` for the supported arguments.
- Build and validate separate indexes before switching consumers across the
  [2.x migration](docs/migrations/v2.md); retain the old index for rollback.

## Reporting issues

Please include:

- input text/file sample
- chunk options
- expected behavior vs actual behavior
- reproduction snippet
- environment (`python --version`, platform)
