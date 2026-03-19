from __future__ import annotations

import asyncio

import pytest

from omnichunk import Chunker, register_formatter, register_parser
from omnichunk.plugins import (
    clear_registry,
    get_formatter,
    get_parser,
    list_registered_formatters,
    list_registered_parsers,
)


@pytest.fixture(autouse=True)
def _clear_plugin_registry() -> None:
    yield
    clear_registry()


def test_register_parser_success() -> None:
    def _p(fp: str, content: str):
        return None

    register_parser("mylang", _p)
    assert get_parser("mylang") is _p


def test_register_parser_duplicate_raises() -> None:
    register_parser("x", lambda a, b: None)
    with pytest.raises(ValueError, match="already registered"):
        register_parser("x", lambda a, b: None)


def test_register_parser_overwrite() -> None:
    def _a(fp: str, c: str):
        return None

    def _b(fp: str, c: str):
        return None

    register_parser("y", _a)
    register_parser("y", _b, overwrite=True)
    assert get_parser("y") is _b


def test_custom_parser_invoked_during_chunk() -> None:
    calls: list[tuple[str, str]] = []

    def _custom(fp: str, content: str):
        calls.append((fp, content))
        return None

    register_parser("python", _custom, overwrite=True)
    chunker = Chunker(max_chunk_size=200, size_unit="chars")
    chunker.chunk("z.py", "def f():\n    return 1\n")
    assert calls == [("z.py", "def f():\n    return 1\n")]


def test_custom_parser_none_falls_through_to_builtin() -> None:
    register_parser("python", lambda fp, c: None, overwrite=True)
    chunker = Chunker(max_chunk_size=200, size_unit="chars")
    chunks = chunker.chunk("ok.py", "def ok():\n    return 0\n")
    assert chunks
    assert any("def ok" in c.text for c in chunks)


def test_register_formatter_duplicate_raises() -> None:
    register_formatter("dup", lambda c: "")
    with pytest.raises(ValueError, match="already registered"):
        register_formatter("dup", lambda c: "x")


def test_formatter_round_trip() -> None:
    def _fmt(chunks: list) -> str:
        return f"n={len(chunks)}"

    register_formatter("mine", _fmt)
    fn = get_formatter("mine")
    assert fn is not None
    assert fn([]) == "n=0"


def test_list_registered_parsers_sorted() -> None:
    register_parser("zebra", lambda a, b: None)
    register_parser("apple", lambda a, b: None)
    assert list_registered_parsers() == ["apple", "zebra"]


def test_clear_registry_empties() -> None:
    register_parser("p", lambda a, b: None)
    register_formatter("f", lambda c: "")
    clear_registry()
    assert list_registered_parsers() == []
    assert list_registered_formatters() == []


def test_astream_still_works_with_plugins_cleared() -> None:
    """Regression: plugin teardown must not break unrelated async API."""
    chunker = Chunker(max_chunk_size=128, size_unit="chars")
    code = "def x():\n    return 2\n"

    async def _run() -> list:
        out = []
        async for ch in chunker.astream("t.py", code):
            out.append(ch)
        return out

    out = asyncio.run(_run())
    assert out
