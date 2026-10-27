"""Source-preserving isolation of documented root statements."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from omnichunk import Chunker
from omnichunk.engine import code_engine
from omnichunk.types import Chunk, ChunkingError


def _assert_source(chunks: list[Chunk], source: str, limit: int, count: Callable[[str], int]):
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.text) <= limit
    assert cursor == len(raw)


@pytest.mark.parametrize("minimum", [0, 90])
def test_independent_documented_policies_are_distinct_despite_soft_minimum(minimum):
    prefix = 'prefix = "' + "x" * 45 + '"\n\n'
    first = "# Enable audited reads only.\nAUDIT_READS = True\n\n"
    second = "# Keep revoked sessions disabled.\nALLOW_REVOKED = False\n\n"
    suffix = 'suffix = "' + "y" * 45 + '"\n'
    source = prefix + first + second + suffix
    chunker = Chunker(
        max_chunk_size=120,
        min_chunk_size=minimum,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("policy.py", source)

    _assert_source(chunks, source, 120, len)
    assert [chunk.text for chunk in chunks] == [prefix, first, second, suffix]
    assert [chunk.text for chunk in chunker.stream("policy.py", source)] == [
        chunk.text for chunk in chunks
    ]


def test_whole_fitting_file_keeps_its_single_chunk_fast_path():
    source = "# First policy.\nFIRST = True\n\n# Second policy.\nSECOND = False\n"
    chunks = Chunker(
        max_chunk_size=120,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    assert [chunk.text for chunk in chunks] == [source]
    _assert_source(chunks, source, 120, len)


def test_isolation_keeps_nonmonotonic_containing_window_when_prefix_would_overflow():
    source = 'one = 1\ntwo = 2\n# policy\nVALUE = 3\n\nsuffix = "' + "z" * 50 + '"\n'

    def count(text: str) -> int:
        return len(text) + (50 if "one" in text and "two" in text and "# policy" not in text else 0)

    chunks = Chunker(
        max_chunk_size=45,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 45, count)
    assert "one" in chunks[0].text and "two" in chunks[0].text and "# policy" in chunks[0].text


def test_isolated_unicode_groups_keep_complete_input_budget_and_metadata():
    prefix = 'prefix = "' + "x" * 45 + '"\r\n\r\n'
    first = "# İzin 確認 😀\r\nAPPROVED = False\r\n\r\n"
    second = "# Keep approvals attributable.\r\nAUDIT = True\r\n\r\n"
    source = prefix + first + second

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2

    chunks = Chunker(
        max_chunk_size=110,
        min_chunk_size=80,
        size_unit="tokens",
        tokenizer=count,
        context_mode="minimal",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 110, count)
    assert [chunk.text for chunk in chunks] == [prefix, first, second]
    assert all(chunk.context.content_type.value == "code" for chunk in chunks)
    assert all(chunk.context.parse_errors == [] for chunk in chunks)


_INLINE_CASES = [
    (
        "policy.py",
        'prefix = "' + "x" * 70 + '"\n\n',
        "# Attached policy\nVALUE = 3  # units are seconds\n\n",
        "# A separate policy\nNEXT = 2\n",
    ),
    (
        "policy.js",
        'const prefix = "' + "x" * 70 + '";\n\n',
        "// Attached policy\nconst value = 3; // units are seconds\n\n",
        "// A separate policy\nconst next = 2;\n",
    ),
    (
        "policy.c",
        'char prefix[] = "' + "x" * 70 + '";\n\n',
        "/* Attached policy */\nint value = 3; /* seconds */ /* audited */\n\n",
        "/* A separate policy */\nint next = 2;\n",
    ),
    (
        "policy.js",
        'const prefix = "' + "x" * 70 + '";\n\n',
        "// Attached policy\nconst value = 3; /* units\n   seconds */ /* audited */\n\n",
        "// A separate policy\nconst next = 2;\n",
    ),
    (
        "policy.c",
        'char prefix[] = "' + "x" * 70 + '";\n\n',
        "/* Attached policy */\nint value = 3; /* units\n   seconds */ /* audited */\n\n",
        "/* A separate policy */\nint next = 2;\n",
    ),
]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(("path", "prefix", "documented", "following"), _INLINE_CASES)
def test_documented_statement_keeps_all_same_line_trailing_comments(
    newline, path, prefix, documented, following
):
    prefix, documented, following = (
        text.replace("\n", newline) for text in (prefix, documented, following)
    )
    source = prefix + documented + following
    chunker = Chunker(
        max_chunk_size=100,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk(path, source)

    _assert_source(chunks, source, 100, len)
    assert [chunk.text for chunk in chunks] == [prefix, documented, following]
    assert [chunk.text for chunk in chunker.stream(path, source)] == [
        chunk.text for chunk in chunks
    ]
    assert all(chunk.context.parse_errors == [] for chunk in chunks)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\u2028", "\u2029"])
@pytest.mark.parametrize("gap", ["\t", "\u00a0", "\u2003"])
def test_javascript_inline_comment_accepts_unicode_whitespace_without_crossing_line_breaks(
    newline, gap
):
    prefix = 'const prefix = "' + "x" * 70 + '";' + newline * 2
    documented = gap + "// Attached policy" + newline
    documented += "const value = 3;" + gap + "// units are seconds" + newline * 2
    following = gap + "// A separate policy" + newline + "const next = 2;" + newline
    source = prefix + documented + following
    chunks = Chunker(
        max_chunk_size=100,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.js", source)

    _assert_source(chunks, source, 100, len)
    assert all(chunk.context.parse_errors == [] for chunk in chunks)
    # Inter-node indentation remains owned by the preceding source slice.
    assert [chunk.text.strip() for chunk in chunks] == [
        text.strip() for text in (prefix, documented, following)
    ]


@pytest.mark.parametrize(
    ("path", "prefix", "leading", "statement_line", "following", "capacity"),
    [
        (
            "policy.py",
            'prefix = "' + "x" * 70 + '"\n\n',
            "# policy\n",
            "VALUE = 3  # units are seconds\n",
            "NEXT = 2\n",
            36,
        ),
        (
            "policy.js",
            'const prefix = "' + "x" * 70 + '";\n\n',
            "// policy\n",
            "const value = 3; // units are seconds\n",
            "const next = 2;\n",
            42,
        ),
        (
            "policy.c",
            'char prefix[] = "' + "x" * 70 + '";\n\n',
            "/* policy */\n",
            "int value = 3; /* units seconds */\n",
            "int next = 2;\n",
            42,
        ),
    ],
)
def test_nonfitting_documented_group_keeps_native_budget_fallback(
    path, prefix, leading, statement_line, following, capacity, monkeypatch
):
    source = prefix + leading + statement_line + following
    arguments = dict(
        max_chunk_size=capacity,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = Chunker(**arguments).chunk(path, source)
    with monkeypatch.context() as patch:
        patch.setattr(code_engine, "_bind_leading_comments", lambda nodes, *_: nodes)
        native = Chunker(**arguments).chunk(path, source)

    _assert_source(chunks, source, capacity, len)
    assert len(leading + statement_line) > capacity
    assert [chunk.text for chunk in chunks] == [chunk.text for chunk in native]


@pytest.mark.parametrize(("path", "prefix", "documented", "following"), _INLINE_CASES[:3])
def test_inline_comment_without_leading_block_keeps_native_ownership(
    path, prefix, documented, following, monkeypatch
):
    statement_line = documented.split("\n", 1)[1].rstrip() + "\n"
    following_statement = following.split("\n", 1)[1]
    source = prefix + statement_line + following_statement
    arguments = dict(
        max_chunk_size=100,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = Chunker(**arguments).chunk(path, source)
    with monkeypatch.context() as patch:
        patch.setattr(code_engine, "_bind_leading_comments", lambda nodes, *_: nodes)
        native = Chunker(**arguments).chunk(path, source)

    _assert_source(chunks, source, 100, len)
    assert [chunk.text for chunk in chunks] == [chunk.text for chunk in native]


def test_trailing_comment_group_uses_nonadditive_full_input_budget():
    source = 'prefix = "' + "x" * 70 + '"\n\n'
    source += "# policy\nVALUE = 3  # units are seconds\nNEXT = 2\n"

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2 + (60 if "VALUE" in text and "# units" in text else 0)

    chunks = Chunker(
        max_chunk_size=75,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 75, count)
    assert not any("VALUE" in chunk.text and "# units" in chunk.text for chunk in chunks)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("policy.py", "# policy\nVALUE = 3  # " + "seconds " * 20 + "\nNEXT = 2\n"),
        ("policy.js", "// policy\nconst value = 3; // " + "seconds " * 20 + "\nconst next = 2;\n"),
        ("policy.c", "/* policy */\nint value = 3; /* " + "seconds " * 20 + "*/\nint next = 2;\n"),
    ],
)
def test_oversized_inline_comment_keeps_explicit_overflow_policy(path, source):
    arguments = dict(
        max_chunk_size=40,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = Chunker(**arguments).chunk(path, source)
    _assert_source(chunks, source, 40, len)
    with pytest.raises(ChunkingError):
        Chunker(**arguments, overflow_policy="error").chunk(path, source)
    preserved = Chunker(**arguments, overflow_policy="preserve").chunk(path, source)
    assert "".join(chunk.text for chunk in preserved) == source
    assert max(len(chunk.text) for chunk in preserved) > 40
