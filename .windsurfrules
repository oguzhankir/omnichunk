# AI Rules & Architecture Manifesto for Omnichunk

These rules apply to ALL AI assistants (Cursor, Windsurf, Claude, Copilot) and human contributors in this repository. Read these carefully before generating any code.

## 0) AI Assistant Persona & Thinking Process
- **Think before you code:** Always analyze the algorithmic complexity (Big-O) of your proposed solution before writing it.
- **Do not invent utilities:** Check existing core modules (like `TextIndex`, `raw_bytes`, AST parsers) before writing new offset calculation or parsing logic.
- **Python first, optimize later:** Do not suggest rewriting in Rust or C unless explicitly instructed. Fix algorithmic bottlenecks in Python first.
- **Zero-copy mindset:** Treat strings as immutable and heavy. Avoid copying, slicing, or duplicating large text blocks in memory.

## 1) Core Engineering Principles
- **Determinism is absolute:** The same input with the same options MUST yield the exact same chunks, byte-for-byte, every single time.
- **Fail loud, or degrade gracefully:** Do not hide failures silently. If a structure cannot be parsed, degrade to a deterministic fallback (e.g., regex or prose engine) and expose the fallback reason in the chunk metadata.
- **Dependency discipline:** Keep the core engine dependency-free (except `tree-sitter`). Tokenizers (`tiktoken`, `transformers`) are optional extras. Do not import them in the critical path without `try/except` blocks.

## 2) Token Optimization & Chunk Boundaries (NEW)
- **Token counting is expensive:** Do not run an LLM tokenizer (like `tiktoken`) on every single AST node or line during the tree traversal.
- **Use fast approximations first:** Use Non-Whitespace (NWS) character counting or byte lengths for initial sizing and windowing. Only invoke the heavy LLM tokenizer at the final boundary validation or if explicitly requested via options.
- **Maximize chunk density:** A chunk should optimally pack as much context as possible up to the `max_size` limit, without breaking semantic boundaries (e.g., don't split mid-function just to save 10 tokens).
- **Cache token counts:** If a specific block's token count is calculated, cache it (or its cumulative sum) to avoid recalculating it during window merges or overlaps.

## 3) Algorithmic Complexity & Hot Paths (CRITICAL)
- **Ban $O(N^2)$ in tight loops:** Never use nested loops or list comprehensions to check overlaps across all chunks or entities. Use Interval Trees, `bisect` (binary search), or sort-and-sweep algorithms for spatial relationships.
- **String operations are toxic in loops:** NEVER use `.splitlines()`, `.count()`, or `re.findall()` inside loops running over large codebases. 
- **Use Bytes, not Strings:** Work with `raw_bytes` and byte offsets. Call `.encode('utf-8')` exactly ONCE per file. Avoid string slicing (`text[a:b]`) until the very end when the final chunk is yielded.
- **Hash primitive values:** Do not use `Enum` objects as dictionary keys or in `set()` lookups in hot paths. Use their primitive values (`enum.value`) to avoid Python's slow enum hashing overhead.

## 4) Mandatory Chunking Invariants
- **Reconstruction:** `original[chunk.byte_range.start:chunk.byte_range.end] == chunk.text` MUST hold true natively.
- **Contiguity:** Chunk ranges must be contiguous in sorted order. No silent gaps, no overlaps (unless overlapping windows are explicitly enabled in settings).
- **No empty yields:** Do not emit empty, whitespace-only, or comment-only chunks.
- **Semantic attachment:** Decorators, docstrings, and function signatures must stay strictly attached to their target definition bodies. Do not split code mid-expression when structural boundaries exist.

## 5) Context and Metadata Rules
- Keep `contextualized_text` logically aligned with the final chunk content. It should contain necessary context (like class names or parent imports) so the chunk makes sense to an LLM in isolation.
- Include only valid metadata derived from parsed or deterministic logic.
- Keep formatting (JSONL, CSV, LangChain Document) consistent and easy to parse for downstream tools.

## 6) Parser and Fallback Behavior
- Prefer `tree-sitter` when the language grammar is available.
- Use iterative (stack/queue based) traversals for deep AST trees. Do not use deep recursion to avoid `RecursionError` on massive files.
- Fallbacks must not violate chunk invariants. If tree-sitter fails, the fallback must still produce perfectly contiguous byte ranges.

## 7) Testing Requirements
Every behavior change must include tests for:
- Correct exact-string reconstruction from chunk ranges.
- Determinism for the same input/options.
- Empty, malformed, and weird Unicode edge cases.
- Engine-specific behavior that changed.
- **Regression:** If fixing a bug, add a specific regression test that fails BEFORE your fix and passes AFTER.

## 8) Rule Synchronization Policy (CI Enforced)
The following files must remain completely identical in content. If you modify these rules, update ALL of them in the same PR:
- `AI_RULES.md`
- `.cursorrules`
- `.windsurfrules`
- `CLAUDE.md`
- `.github/copilot-instructions.md`