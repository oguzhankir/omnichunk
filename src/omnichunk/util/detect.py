from __future__ import annotations

import ast
import re
from pathlib import Path

from omnichunk.types import ContentType, Language

_EXTENSION_LANGUAGE: dict[str, Language] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".hs": "haskell",
    ".lua": "lua",
    ".zig": "zig",
    ".ex": "elixir",
    ".exs": "elixir",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "markdown",
    ".txt": "plaintext",
    ".rst": "rst",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".jsonl": "json",
    ".toml": "toml",
    ".ipynb": "jupyter",
    ".tex": "latex",
    ".pdf": "pdf",
    ".docx": "docx",
}

_CODE_LANGUAGES: set[Language] = {
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "haskell",
    "lua",
    "zig",
    "elixir",
    "sql",
    "bash",
}

_MARKUP_LANGUAGES: set[Language] = {"html", "xml", "yaml", "json", "toml"}

_PROSE_LANGUAGES: set[Language] = {"markdown", "plaintext", "latex", "pdf", "docx", "rst"}


def detect_language(filepath: str = "", content: str = "") -> Language:
    """Detect language from path first, then lightweight content heuristics."""
    if filepath:
        path = Path(filepath.lower())
        suffixes = path.suffixes
        if suffixes:
            compound = "".join(suffixes[-2:])
            if compound == ".d.ts":
                return "typescript"
        for suffix in reversed(suffixes):
            if suffix in _EXTENSION_LANGUAGE:
                return _EXTENSION_LANGUAGE[suffix]

    if not content:
        return "plaintext"

    stripped = content.lstrip()

    if re.search(r"^\s*#{1,6}\s+.+$", content, flags=re.MULTILINE):
        return "markdown"
    if stripped.startswith("<!DOCTYPE html") or re.search(r"<html[\s>]", stripped, flags=re.I):
        return "html"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if re.search(r"^\s*def\s+\w+\s*\(", content, flags=re.MULTILINE):
        return "python"
    if re.search(r"\b(function|const|let|class|interface)\b", content):
        return "typescript"
    if re.search(r"\bpackage\s+\w+", content) and "func " in content:
        return "go"
    if re.search(r"\bfn\s+\w+", content) and "impl" in content:
        return "rust"

    return "plaintext"


def detect_content_type(
    filepath: str = "",
    content: str = "",
    language: Language | None = None,
) -> ContentType:
    """Detect high-level content category."""
    lang = language or detect_language(filepath=filepath, content=content)

    path_lower = filepath.lower() if filepath else ""
    if path_lower.endswith(".ipynb") or lang == "jupyter":
        return ContentType.HYBRID

    if filepath.endswith(".mdx") or "# %%" in content:
        return ContentType.HYBRID

    if lang in _CODE_LANGUAGES:
        if lang == "python" and _looks_hybrid_python(content):
            return ContentType.HYBRID
        return ContentType.CODE

    if lang in _MARKUP_LANGUAGES:
        return ContentType.MARKUP

    if lang in _PROSE_LANGUAGES:
        return ContentType.PROSE

    if _looks_like_markup(content):
        return ContentType.MARKUP
    if _looks_like_code(content):
        return ContentType.CODE

    return ContentType.PROSE


def _looks_like_code(content: str) -> bool:
    if not content:
        return False
    code_signals = [
        r"\bdef\s+\w+\s*\(",
        r"\bclass\s+\w+",
        r"\bfunction\s+\w+\s*\(",
        r"\bimport\s+[\w\.\*\{\}\,\s]+",
        r"\breturn\b",
        r"\{\s*$",
    ]
    score = sum(bool(re.search(sig, content, re.MULTILINE)) for sig in code_signals)
    return score >= 2


def _looks_like_markup(content: str) -> bool:
    if not content:
        return False
    stripped = content.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return True
    if re.search(r"<\/?[a-zA-Z][^>]*>", content):
        return True
    return bool(re.search(r"^\s*[\w\-\.]+\s*:\s*.+$", content, flags=re.MULTILINE))


def _looks_hybrid_python(content: str) -> bool:
    """Detect documentation-heavy valid Python without treating data as prose.

    Python defines docstrings only as the first string expression in a module,
    class, function or async function body. Source lengths include the original
    literal syntax and use AST UTF-8 byte columns, not decoded string lengths.
    """
    if not content:
        return False
    try:
        tree = ast.parse(content)
        raw = content.encode("utf-8")
    except (SyntaxError, ValueError, RecursionError, UnicodeError):
        # Partial or malformed source still belongs to the code engine, whose
        # parser diagnostics/fallbacks can describe the input to the caller.
        return False
    line_starts = [0, *(match.end() for match in re.finditer(rb"\r\n?|\n", raw))]
    doc_bytes = 0
    # Definitions can be nested in statement suites, including handlers and
    # match cases, but never inside expressions. Avoid visiting expression trees.
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        if (
            isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
        ):
            value = node.body[0].value
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.end_lineno is not None
                and value.end_col_offset is not None
            ):
                start = line_starts[value.lineno - 1] + value.col_offset
                end = line_starts[value.end_lineno - 1] + value.end_col_offset
                doc_bytes += end - start
        for _, field in ast.iter_fields(node):
            if isinstance(field, list):
                pending.extend(
                    child
                    for child in field
                    if isinstance(child, ast.stmt | ast.ExceptHandler | ast.match_case)
                )
    return doc_bytes > 0 and doc_bytes / len(raw) > 0.4
