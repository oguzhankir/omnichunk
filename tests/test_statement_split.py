from __future__ import annotations

from omnichunk import Chunker
from omnichunk.sizing.nws import preprocess_nws_cumsum
from omnichunk.windowing.models import ASTNodeWindowItem
from omnichunk.windowing.split import find_statement_boundary, split_oversized_leaf


def test_find_statement_boundary_ignores_newlines_inside_triple_quoted_string() -> None:
    src = b'x = """\na\nb\n"""\n'
    open_q = src.index(b'"""') + 3
    first_inner_nl = src.index(b"\n", open_q)
    cand_inside = first_inner_nl + 1
    assert find_statement_boundary(src, 0, cand_inside, len(src)) == cand_inside

    after_close = src.index(b'"""', open_q) + 3
    after_stmt_nl = src.index(b"\n", after_close) + 1
    assert find_statement_boundary(src, 0, len(src), len(src)) == after_stmt_nl


def test_find_statement_boundary_prefers_last_newline_before_candidate() -> None:
    src = b"line1;\nline2;\nzzz"
    e2 = len(b"line1;\nline2;\n")
    assert find_statement_boundary(src, 0, len(src), len(src)) == e2
    mid = e2 - 2
    assert find_statement_boundary(src, 0, mid, len(src)) == len(b"line1;\n")


def test_split_oversized_leaf_reconstruction_and_determinism() -> None:
    # Force hard-split path: long lines with semicolons so statement boundaries exist.
    line = "x = 1; y = 2; z = 3; " + "w" * 80 + "\n"
    code = "def huge():\n    " + line * 12
    cum = preprocess_nws_cumsum(code, backend="python")
    text_b = code.encode("utf-8")
    start = text_b.index(b"def huge")
    end = len(text_b)
    item = ASTNodeWindowItem(node=None, start=start, end=end, size=10**9)

    def run() -> list[tuple[int, int]]:
        return [
            (it.start, it.end)
            for it in split_oversized_leaf(item, code=code, cumsum=cum, max_size=120)
        ]

    a = run()
    b = run()
    assert a == b
    joined = b"".join(text_b[s:e] for s, e in a)
    assert joined == text_b[start:end]


def test_no_chunk_ends_inside_quoted_region_when_newlines_outside() -> None:
    """Triple-quoted block: no chunk boundary may fall inside the literal."""
    filler = "word " * 30
    code = (
        "def outer():\n"
        '    s = """\n'
        f"{filler}\n"
        f"{filler}\n"
        '    """\n'
        "    return s\n"
    )
    chunker = Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars")
    chunks = chunker.chunk("m.py", code)
    assert "".join(c.text for c in chunks) == code
    q_open = code.index('"""')
    q_close = code.index('"""', q_open + 3) + 3
    for c in chunks:
        br = c.byte_range
        if br.start < q_open < br.end:
            assert br.end <= q_open or br.start >= q_close


def test_nested_class_methods_small_max_reconstruction() -> None:
    code = (
        "class C:\n"
        "    def a(self):\n"
        "        return 1\n"
        "    def b(self):\n"
        "        return 2\n"
        "    def c(self):\n"
        "        return 3\n"
    )
    chunker = Chunker(max_chunk_size=45, min_chunk_size=8, size_unit="chars")
    chunks = chunker.chunk("cls.py", code)
    assert "".join(c.text for c in chunks) == code
    a1 = chunker.chunk("cls.py", code)
    a2 = chunker.chunk("cls.py", code)
    assert [c.text for c in a1] == [c.text for c in a2]
