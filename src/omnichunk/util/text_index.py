from __future__ import annotations

from bisect import bisect_right


class TextIndex:
    """Precomputed mappings for fast byte/line lookups over a text string."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._raw_bytes = text.encode("utf-8")

        self._char_to_byte: list[int] = [0] * (len(text) + 1)
        self._line_starts: list[int] = [0]

        byte_cursor = 0
        for idx, ch in enumerate(text):
            self._char_to_byte[idx] = byte_cursor
            byte_cursor += len(ch.encode("utf-8"))
            if ch == "\n":
                self._line_starts.append(idx + 1)
        self._char_to_byte[len(text)] = byte_cursor

        self._newline_bytes = [idx for idx, b in enumerate(self._raw_bytes) if b == 10]

    @property
    def raw_bytes(self) -> bytes:
        return self._raw_bytes

    def byte_offset_for_char(self, char_index: int) -> int:
        if char_index <= 0:
            return 0
        if char_index >= len(self._char_to_byte):
            return self._char_to_byte[-1]
        return self._char_to_byte[char_index]

    def line_for_char(self, char_index: int) -> int:
        if char_index <= 0:
            return 0
        idx = bisect_right(self._line_starts, char_index) - 1
        return max(0, idx)

    def line_for_byte(self, byte_offset: int) -> int:
        if byte_offset <= 0:
            return 0
        return bisect_right(self._newline_bytes, byte_offset - 1)
