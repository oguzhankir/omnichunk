"""
Plugin parsers/formatters: register for a language without tree-sitter grammar (lua), cleanup.
"""

from __future__ import annotations

import sys
from pathlib import Path

repo_src = Path(__file__).resolve().parents[1] / "src"
if repo_src.exists():
    sys.path.insert(0, str(repo_src))

from omnichunk import Chunker
from omnichunk.plugins import (
    clear_registry,
    get_formatter,
    get_parser,
    list_registered_formatters,
    list_registered_parsers,
    register_formatter,
    register_parser,
)
from omnichunk.types import ContentType


def main() -> None:
    class _Root:
        has_error = False

    class _Tree:
        root_node = _Root()

    called = {"n": 0}

    def demo_lua_parser(filepath: str, content: str) -> object:
        called["n"] += 1
        return _Tree()

    register_parser("lua", demo_lua_parser, overwrite=True)
    print("parsers:", list_registered_parsers())
    assert get_parser("lua") is demo_lua_parser

    chunker = Chunker(
        max_chunk_size=120,
        size_unit="chars",
        language="lua",
        content_type=ContentType.CODE,
    )
    chunks = chunker.chunk("demo.lua", "function foo() return 1 end\n")
    print(f"lua chunks: {len(chunks)} plugin_calls={called['n']}")

    register_formatter(
        "yaml_like",
        lambda chs: "\n".join(f"- text: {c.text[:40]!r}" for c in chs),
        overwrite=True,
    )
    fmt = get_formatter("yaml_like")
    assert fmt is not None
    out = fmt(chunks)
    print("formatters:", list_registered_formatters())
    print("yaml_like output:\n", out[:200])

    clear_registry()
    print("after clear_registry: parsers=", list_registered_parsers())


if __name__ == "__main__":
    main()
