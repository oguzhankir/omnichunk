"""Instance-scoped parser hooks and formatters, with explicit fallback behavior."""

from __future__ import annotations

import sys
from pathlib import Path

repo_src = Path(__file__).resolve().parents[1] / "src"
if repo_src.exists():
    sys.path.insert(0, str(repo_src))

from omnichunk import Chunker, PluginRegistry
from omnichunk.types import ContentType


def main() -> None:
    registry = PluginRegistry(revision="example-v1")
    calls: list[str] = []

    def optional_lua_parser(filepath: str, content: str) -> None:
        # A real integration returns a compatible syntax tree. Returning None
        # deliberately delegates to the diagnosed built-in fallback.
        calls.append(filepath)
        return None

    registry.register_parser("lua", optional_lua_parser)
    registry.register_formatter(
        "yaml_like", lambda chunks: "\n".join(f"- text: {c.text[:40]!r}" for c in chunks)
    )
    chunker = Chunker(
        registry=registry,
        max_chunk_size=120,
        language="lua",
        content_type=ContentType.CODE,
    )
    chunks = chunker.chunk("demo.lua", "function foo() return 1 end\n")
    assert calls == ["demo.lua"]
    print(f"lua chunks: {len(chunks)}")
    print("parser diagnostics:", chunks[0].context.parse_errors)
    print(chunker.format(chunks, "yaml_like"))

    # Another pipeline receives its own empty registry.
    separate = Chunker(registry=PluginRegistry())
    assert not separate.registry.parsers and not separate.registry.formatters


if __name__ == "__main__":
    main()
