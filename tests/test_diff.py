from __future__ import annotations

import pytest

from omnichunk import Chunker, chunks_to_pinecone_vectors, stable_chunk_id
from omnichunk.diff.engine import chunk_diff


def _ids(chunks: list) -> set[str]:
    return {stable_chunk_id(c) for c in chunks}


def test_chunk_diff_no_change() -> None:
    code = "def foo():\n    return 1\n" * 10
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks_v1 = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", code, previous_chunks=chunks_v1)
    assert diff.total_added == 0
    assert diff.total_removed == 0
    assert diff.total_unchanged == len(chunks_v1)


def test_chunk_diff_append_only() -> None:
    base = ("hello world\n") * 10
    new = base + ("goodbye\n") * 5
    chunker = Chunker(max_chunk_size=120, size_unit="chars", min_chunk_size=1)
    chunks_v1 = chunker.chunk("m.txt", base)
    diff = chunker.chunk_diff("m.txt", new, previous_chunks=chunks_v1)
    assert diff.total_added > 0
    assert diff.total_removed == 0


def test_chunk_diff_delete_section() -> None:
    full = "def foo():\n    return 1\n" * 10 + "def bar():\n    return 2\n" * 10
    trimmed = "def foo():\n    return 1\n" * 10
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks_full = chunker.chunk("m.py", full)
    diff = chunker.chunk_diff("m.py", trimmed, previous_chunks=chunks_full)
    assert diff.total_removed > 0


def test_chunk_diff_removed_ids_are_strings() -> None:
    code = "def f():\n    pass\n" * 8
    new_code = "def g():\n    pass\n" * 8
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    old_chunks = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", new_code, previous_chunks=old_chunks)
    for rid in diff.removed_ids:
        assert isinstance(rid, str)
        assert len(rid) == 64


def test_chunk_diff_empty_previous() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    diff = chunker.chunk_diff("m.py", code, previous_chunks=[])
    new_chunks = chunker.chunk("m.py", code)
    assert diff.total_added == len(new_chunks)
    assert diff.total_unchanged == 0
    assert diff.total_removed == 0


def test_chunk_diff_empty_new_content() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    old_chunks = chunker.chunk("m.py", code)
    diff = chunker.chunk_diff("m.py", "", previous_chunks=old_chunks)
    assert diff.total_removed == len(old_chunks)
    assert diff.total_added == 0


def test_stable_chunk_id_deterministic() -> None:
    code = "def f():\n    pass\n"
    chunker = Chunker(max_chunk_size=64, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    ids1 = [stable_chunk_id(c) for c in chunks]
    ids2 = [stable_chunk_id(c) for c in chunks]
    assert ids1 == ids2


def test_chunk_diff_consistent_with_pinecone_ids() -> None:
    code = "def f():\n    pass\n" * 5
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    embeddings = [[0.0] * 4 for _ in chunks]
    vecs = chunks_to_pinecone_vectors(chunks, embeddings)
    pinecone_ids = [v["id"] for v in vecs]
    stable_ids = [stable_chunk_id(c) for c in chunks]
    assert pinecone_ids == stable_ids


@pytest.mark.parametrize(
    "filepath,body_lines",
    [
        ("a.py", ("def x():\n    pass\n",) * 3),
        ("dir/b.md", ("# H\n", "para\n", "para2\n")),
        ("plain.txt", ("x\n", "y\n", "z\n", "w\n")),
        ("unicode_🙂.txt", ("line α\n", "line β\n", "line γ\n")),
    ],
)
def test_identical_documents_zero_diff(filepath: str, body_lines: tuple[str, ...]) -> None:
    content = "".join(body_lines)
    chunker = Chunker(max_chunk_size=40, size_unit="chars", min_chunk_size=1)
    prev = chunker.chunk(filepath, content)
    diff = chunker.chunk_diff(filepath, content, previous_chunks=prev)
    assert diff.total_added == 0 and diff.total_removed == 0
    assert diff.total_unchanged == len(prev)
    assert _ids(diff.unchanged) == _ids(prev)


@pytest.mark.parametrize(
    "old_body,new_body",
    [
        (
            "\n".join(f"alpha_{i:03d}_short" for i in range(24)) + "\n",
            "\n".join(f"omega_{i:03d}_XXXXXXXX_longer" for i in range(24)) + "\n",
        ),
        (
            "\n".join(f"import x #{i:04d}" for i in range(18)) + "\n",
            "\n".join(f"export zzz #{i:04d}" for i in range(18)) + "\n",
        ),
    ],
)
def test_completely_replaced_all_added_all_removed(old_body: str, new_body: str) -> None:
    fp = "swap.py"
    chunker = Chunker(max_chunk_size=36, size_unit="chars", min_chunk_size=1)
    prev = chunker.chunk(fp, old_body)
    diff = chunker.chunk_diff(fp, new_body, previous_chunks=prev)
    fresh = chunker.chunk(fp, new_body)
    assert _ids(prev).isdisjoint(_ids(fresh)), "bodies must yield disjoint stable ID sets"
    assert diff.total_removed == len(prev)
    assert diff.total_added == len(fresh)
    assert diff.total_unchanged == 0
    assert set(diff.removed_ids) == _ids(prev)
    assert _ids(diff.added) == _ids(fresh)


@pytest.mark.parametrize(
    "base,insert_at,insert_char",
    [
        ("abcdefghijklmnop\n" * 4, 10, "Z"),
        ("print('hi')\n" * 6, 5, "X"),
        ("0123456789\n" * 3, 3, "π"),
    ],
)
def test_single_character_insertion_mid_file(
    base: str, insert_at: int, insert_char: str
) -> None:
    assert len(insert_char) == 1
    new_content = base[:insert_at] + insert_char + base[insert_at:]
    chunker = Chunker(max_chunk_size=48, size_unit="chars", min_chunk_size=1)
    fp = "mid.py"
    prev = chunker.chunk(fp, base)
    diff = chunker.chunk_diff(fp, new_content, previous_chunks=prev)
    assert diff.total_added >= 1
    assert diff.total_removed >= 1
    assert diff.total_added + diff.total_unchanged == len(chunker.chunk(fp, new_content))


@pytest.mark.parametrize(
    "lines",
    [
        ("first\n", "middlemiddle\n", "z\n"),
        ("one\n", "twoline\n", "x\n"),
        ("p\n", "qq\n", "r\n", "ss\n", "uuuuu\n"),
    ],
)
def test_line_reorder_without_changing_multiset(lines: tuple[str, ...]) -> None:
    """Same multiset of lines; order differs enough that chunk byte windows shift."""
    ordered = "".join(lines)
    reordered = "".join(reversed(lines))
    assert sorted(ordered.splitlines()) == sorted(reordered.splitlines())
    chunker = Chunker(max_chunk_size=10, size_unit="chars", min_chunk_size=1)
    fp = "order.txt"
    prev = chunker.chunk(fp, ordered)
    fresh = chunker.chunk(fp, reordered)
    diff = chunker.chunk_diff(fp, reordered, previous_chunks=prev)
    assert ordered != reordered
    assert _ids(prev) != _ids(fresh)
    assert diff.total_removed >= 1 and diff.total_added >= 1


@pytest.mark.parametrize(
    "old_t,new_t",
    [
        ("café résumé " * 8 + "\n", "cafè résumé " * 7 + "DIFFERENT_TAIL\n"),
        ("hello 🙂 " * 6 + "\n", "hello 🙃 " * 5 + "morebytes\n"),
        ("日本語\n" * 10 + "ko\n", "日本語\n" * 8 + "한국어\n" * 3),
        ("𝔸𝔹ℂ\n" * 9, "𝔸𝔻ℂ\n" * 7 + "𝕏\n"),
    ],
)
def test_emoji_and_multibyte_unicode_changes(old_t: str, new_t: str) -> None:
    chunker = Chunker(max_chunk_size=28, size_unit="chars", min_chunk_size=1)
    fp = "utf8.txt"
    prev = chunker.chunk(fp, old_t)
    diff = chunker.chunk_diff(fp, new_t, previous_chunks=prev)
    fresh = chunker.chunk(fp, new_t)
    assert _ids(prev) != _ids(fresh)
    assert diff.total_added >= 1 and diff.total_removed >= 1
    assert diff.total_added + diff.total_unchanged == len(fresh)


@pytest.mark.parametrize(
    "content_a,content_b,max_size",
    [
        ("def a():\n  return 1\n" * 4, "def a():\n  return 2\n" * 4, 40),
        ("x\n" * 20, "x\n" * 18 + "z\n" * 2, 16),
        ("# t\n" + "body\n" * 12, "# t\n" + "body\n" * 11 + "tail\n", 28),
    ],
)
def test_diff_then_ids_match_fresh_chunk(
    content_a: str, content_b: str, max_size: int
) -> None:
    fp = "fresh.py"
    chunker = Chunker(max_chunk_size=max_size, size_unit="chars", min_chunk_size=1)
    prev = chunker.chunk(fp, content_a)
    diff = chunker.chunk_diff(fp, content_b, previous_chunks=prev)
    fresh_chunks = chunker.chunk(fp, content_b)
    combined_ids = _ids(diff.added) | _ids(diff.unchanged)
    assert combined_ids == _ids(fresh_chunks)
    assert diff.total_added + diff.total_unchanged == len(fresh_chunks)


@pytest.mark.parametrize(
    "core_tail",
    [
        "\n  \n\t  \n",
        "\n\n",
        " \n \n",
    ],
)
def test_stable_ids_unchanged_prefix_after_whitespace_only_suffix(core_tail: str) -> None:
    base = "solo_line\n" * 15
    chunker = Chunker(max_chunk_size=30, size_unit="chars", min_chunk_size=1)
    fp = "ws.txt"
    prev = chunker.chunk(fp, base)
    new_content = base + core_tail
    diff = chunker.chunk_diff(fp, new_content, previous_chunks=prev)
    first_prev_id = stable_chunk_id(prev[0])
    unchanged_ids = {stable_chunk_id(c) for c in diff.unchanged}
    assert first_prev_id in unchanged_ids


@pytest.mark.parametrize(
    "initial,final,expect_added,expect_removed",
    [
        ("", "start\n", True, False),
        ("chunk\n" * 3, "", False, True),
        ("", "", False, False),
    ],
)
def test_empty_to_nonempty_and_nonempty_to_empty(
    initial: str,
    final: str,
    expect_added: bool,
    expect_removed: bool,
) -> None:
    chunker = Chunker(max_chunk_size=20, size_unit="chars", min_chunk_size=1)
    fp = "edge.py"
    prev = chunker.chunk(fp, initial)
    diff = chunker.chunk_diff(fp, final, previous_chunks=prev)
    assert (diff.total_added > 0) == expect_added
    assert (diff.total_removed > 0) == expect_removed


@pytest.mark.parametrize(
    "content",
    [
        "export const x = 1;\n" * 5,
        "def shared():\n    return 0\n" * 4,
    ],
)
def test_diff_when_filepath_extension_changes(content: str) -> None:
    chunker = Chunker(max_chunk_size=36, size_unit="chars", min_chunk_size=1)
    prev_py = chunker.chunk("mod.py", content)
    diff = chunker.chunk_diff("mod.ts", content, previous_chunks=prev_py)
    fresh_ts = chunker.chunk("mod.ts", content)
    assert diff.total_removed == len(prev_py)
    assert _ids(diff.added) == _ids(fresh_ts)
    assert diff.total_unchanged == 0


@pytest.mark.parametrize(
    "filler,max_size",
    [
        ("abcdefghijklmnopqrst", 20),
        ("1234567890123456789", 19),
    ],
)
def test_content_exceeding_max_chunk_size_by_one_char(filler: str, max_size: int) -> None:
    assert len(filler) == max_size
    one_long = filler + "X"
    chunker = Chunker(max_chunk_size=max_size, size_unit="chars", min_chunk_size=1)
    fp = "wide.txt"
    prev = chunker.chunk(fp, filler)
    diff = chunker.chunk_diff(fp, one_long, previous_chunks=prev)
    assert len(chunker.chunk(fp, one_long)) >= 1
    assert diff.total_added >= 1 and diff.total_removed >= 1


@pytest.mark.parametrize(
    "max_sz,min_sz",
    [(56, 4), (72, 6)],
)
def test_chunk_diff_engine_default_chunker_branch(max_sz: int, min_sz: int) -> None:
    text = "def u():\n    return 3\n" * 6
    fp = "direct.py"
    chunker = Chunker(max_chunk_size=max_sz, size_unit="chars", min_chunk_size=min_sz)
    prev = chunker.chunk(fp, text)
    same = chunk_diff(
        fp,
        text,
        previous_chunks=prev,
        chunker=None,
        max_chunk_size=max_sz,
        size_unit="chars",
        min_chunk_size=min_sz,
    )
    assert same.total_added == same.total_removed == 0
    explicit = chunk_diff(fp, text, previous_chunks=prev, chunker=chunker)
    assert explicit.total_added == explicit.total_removed == 0


def test_chunk_diff_engine_passes_explicit_chunker_instance() -> None:
    body = "a\n" * 25
    fp = "x.txt"
    ch = Chunker(max_chunk_size=10, size_unit="chars", min_chunk_size=1)
    prev = ch.chunk(fp, body)
    diff = chunk_diff(fp, body + "z\n", previous_chunks=prev, chunker=ch)
    assert diff.total_added >= 1
