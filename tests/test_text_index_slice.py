from __future__ import annotations

from omnichunk.util.text_index import TextIndex


def test_from_parent_slice_matches_fresh_index() -> None:
    text = "aa\nbb\ncc\ndd"
    parent = TextIndex(text)
    for lo, hi in ((0, len(text)), (2, 8), (3, 4)):
        sub = text[lo:hi]
        sliced = TextIndex.from_parent_slice(parent, lo, hi)
        fresh = TextIndex(sub)
        assert sliced.raw_bytes == fresh.raw_bytes
        for i in range(len(sub) + 1):
            assert sliced.byte_offset_for_char(i) == fresh.byte_offset_for_char(i)
        last_ci = max(0, len(sub) - 1)
        assert sliced.line_for_char(last_ci) == fresh.line_for_char(last_ci)
