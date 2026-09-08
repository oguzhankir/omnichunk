from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from omnichunk.types import Language

from .languages import get_parser as get_ts_parser


@dataclass(frozen=True)
class ParseResult:
    tree: Any | None
    errors: list[str] = field(default_factory=list)
    backend: str = "none"


def parse_code(
    code: str,
    language: Language,
    *,
    filepath: str = "",
) -> ParseResult:
    """Parse source code with an optional plugin parser, then tree-sitter when available."""
    from omnichunk import plugins as _plugins

    errors: list[str] = []
    custom = _plugins.get_parser(str(language))
    if custom is not None:
        try:
            result = custom(filepath, code)
            if result is not None:
                root = getattr(result, "root_node", None)
                if root is not None:
                    has_error = getattr(root, "has_error", False)
                    if has_error:
                        errors.append("Tree contains syntax error nodes")
                    return ParseResult(tree=result, errors=errors, backend="plugin")
                errors.append("Plugin parser returned no root node; trying tree-sitter")
            else:
                errors.append("Plugin parser declined input; trying tree-sitter")
        except Exception as exc:
            errors.append(f"Plugin parser failed: {type(exc).__name__}; trying tree-sitter")

    parser = get_ts_parser(language)
    if parser is None:
        backend = "regex" if language == "python" else "plain"
        errors.append(f"No tree-sitter parser available for '{language}'; fallback={backend}")
        return ParseResult(tree=None, errors=errors, backend=backend)

    raw_bytes = code.encode("utf-8")
    try:
        tree = parser.parse(raw_bytes)
    except Exception as exc:
        backend = "regex" if language == "python" else "plain"
        errors.append(f"Tree-sitter parse failed: {type(exc).__name__}; fallback={backend}")
        return ParseResult(tree=None, errors=errors, backend=backend)

    root = getattr(tree, "root_node", None)
    if root is not None:
        has_error = getattr(root, "has_error", False)
        if has_error:
            errors.append("Tree contains syntax error nodes")
    return ParseResult(tree=tree, errors=errors, backend="tree-sitter")
