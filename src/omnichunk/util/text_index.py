from __future__ import annotations

from bisect import bisect_right
from typing import Any

_rust_mod: Any | None = None
_rust_tried = False


def _get_rust_mod() -> Any | None:
    global _rust_mod, _rust_tried
    if _rust_tried:
        return _rust_mod
    _rust_tried = True
    try:
        import importlib
        mod = importlib.import_module("omnichunk_rust")
        if callable(getattr(mod, "build_char_to_byte_index", None)):
            _rust_mod = mod
    except Exception:
        pass
    return _rust_mod


class TextIndex:
    """Precomputed mappings for fast byte/line lookups over a text string."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._raw_bytes = text.encode("utf-8")

        rust = _get_rust_mod()
        if rust is not None:
            char_to_byte, line_starts = rust.build_char_to_byte_index(self._raw_bytes)
            self._char_to_byte: list[int] = list(char_to_byte)
            self._line_starts: list[int] = list(line_starts)
        else:
            self._char_to_byte = [0] * (len(text) + 1)
            self._line_starts = [0]
            byte_cursor = 0
            for idx, ch in enumerate(text):
                self._char_to_byte[idx] = byte_cursor
                cp = ord(ch)
                if cp < 0x80:
                    byte_cursor += 1
                elif cp < 0x800:
                    byte_cursor += 2
                elif cp < 0x10000:
                    byte_cursor += 3
                else:
                    byte_cursor += 4
                if ch == "\n":
                    self._line_starts.append(idx + 1)
            self._char_to_byte[len(text)] = byte_cursor

        self._newline_bytes = [idx for idx, b in enumerate(self._raw_bytes) if b == 10]

    @classmethod
    def from_parent_slice(cls, parent: TextIndex, char_start: int, char_end: int) -> TextIndex:
        """Slice of ``parent._text[char_start:char_end]`` without re-encoding the full string."""
        if char_end < char_start:
            char_end = char_start
        sub_text = parent._text[char_start:char_end]
        inst = object.__new__(cls)
        inst._text = sub_text
        b0 = parent.byte_offset_for_char(char_start)
        b1 = parent.byte_offset_for_char(char_end)
        inst._raw_bytes = parent._raw_bytes[b0:b1]
        n = len(sub_text)
        inst._char_to_byte = [
            parent.byte_offset_for_char(char_start + i) - b0 for i in range(n + 1)
        ]
        inst._line_starts = [0]
        for ls in parent._line_starts:
            if ls <= char_start:
                continue
            if ls >= char_end:
                break
            inst._line_starts.append(ls - char_start)
        inst._newline_bytes = [nb - b0 for nb in parent._newline_bytes if b0 <= nb < b1]
        return inst

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
