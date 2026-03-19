# AI Rules for Omnichunk

These rules apply to all AI assistants and contributors in this repository.

## 1) Core engineering principles

- Keep changes deterministic.
- Prefer simple, explicit implementations.
- Do not hide failures silently.
- Preserve byte-range integrity for all chunk outputs.
- Avoid adding complexity unless there is a measured benefit.

## 2) Mandatory chunking invariants

- `original[chunk.byte_range.start:chunk.byte_range.end] == chunk.text` must hold.
- Chunk ranges must be contiguous in sorted order (no gaps, no overlaps).
- Do not emit empty or whitespace-only chunks.
- Decorators must stay attached to their target definitions.
- Do not split code mid-expression when structural boundaries exist.

## 3) Context and metadata rules

- Keep `contextualized_text` aligned with the final chunk content.
- Include only valid metadata derived from parsed or deterministic logic.
- Keep formatting consistent and easy to parse.
- If parser errors exist, expose them via context instead of masking.

## 4) Parser and fallback behavior

- Prefer tree-sitter when grammar is available.
- Use iterative traversals for deep trees.
- When parser support is missing, degrade gracefully with deterministic fallbacks.
- Fallbacks must not violate chunk invariants.

## 5) Performance expectations

- Avoid repeated full-string scans in chunk loops.
- Reuse precomputed indices and counters where possible.
- Keep algorithmic complexity visible in code.
- Add benchmarks for performance-sensitive changes.

## 6) Testing requirements

Every behavior change must include tests for:

- Correct reconstruction from chunk ranges
- Determinism for same input/options
- Empty/malformed/unicode edge cases
- Engine-specific behavior that changed

If fixing a bug, add a regression test that fails before and passes after.

## 7) Code style and review rules

- Use type hints on public functions.
- Keep functions focused; avoid oversized methods.
- Do not introduce unrelated refactors in bug-fix PRs.
- Update docs when API/behavior changes.

## 8) PR checklist (required)

- [ ] Added or updated tests
- [ ] Verified local `pytest -q`
- [ ] Updated docs/README when needed
- [ ] Preserved chunk invariants
- [ ] Kept rule files synchronized

## 9) Rule synchronization policy

The following files must remain identical in content:

- `AI_RULES.md`
- `.cursorrules`
- `.windsurfrules`
- `CLAUDE.md`
- `.github/copilot-instructions.md`

CI enforces this. If you change one, update all of them in the same PR.
