from __future__ import annotations

from pathlib import Path
import re

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
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "markdown",
    ".txt": "plaintext",
    ".rst": "plaintext",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".jsonl": "json",
    ".toml": "toml",
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
}

_MARKUP_LANGUAGES: set[Language] = {"html", "xml", "yaml", "json", "toml"}

_PROSE_LANGUAGES: set[Language] = {"markdown", "plaintext"}


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
    if re.search(r"^\s*[\w\-\.]+\s*:\s*.+$", content, flags=re.MULTILINE):
        return True
    return False


def _looks_hybrid_python(content: str) -> bool:
    if not content:
        return False
    docstrings = re.findall(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', content)
    doc_chars = sum(len(ds) for ds in docstrings)
    return doc_chars > 0 and doc_chars / max(len(content), 1) > 0.4
