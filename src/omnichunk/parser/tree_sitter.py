from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from omnichunk.types import Language

from .languages import get_parser


@dataclass(frozen=True)
class ParseResult:
    tree: Any | None
    errors: list[str] = field(default_factory=list)


def parse_code(code: str, language: Language) -> ParseResult:
    """Parse source code with tree-sitter when grammar is available."""
    parser = get_parser(language)
    if parser is None:
        return ParseResult(tree=None, errors=[f"No tree-sitter parser available for '{language}'"])

    raw_bytes = code.encode("utf-8")
    try:
        tree = parser.parse(raw_bytes)
    except Exception as exc:
        return ParseResult(tree=None, errors=[f"Tree-sitter parse failed: {exc}"])

    errors: list[str] = []
    root = getattr(tree, "root_node", None)
    if root is not None:
        has_error = getattr(root, "has_error", False)
        if has_error:
            errors.append("Tree contains syntax error nodes")
    return ParseResult(tree=tree, errors=errors)
