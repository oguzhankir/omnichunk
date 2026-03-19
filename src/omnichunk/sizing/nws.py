from __future__ import annotations

import numpy as np

_WHITESPACE_BYTES = np.array([9, 10, 11, 12, 13, 32], dtype=np.uint8)


def preprocess_nws_cumsum(code: str) -> np.ndarray:
    """Build cumulative non-whitespace byte counts for O(1) range queries."""
    if not code:
        return np.array([0], dtype=np.int64)

    raw = np.frombuffer(code.encode("utf-8"), dtype=np.uint8)
    mask = ~np.isin(raw, _WHITESPACE_BYTES)
    cumsum = np.empty(mask.shape[0] + 1, dtype=np.int64)
    cumsum[0] = 0
    np.cumsum(mask, out=cumsum[1:])
    return cumsum


def get_nws_count(cumsum: np.ndarray, start: int, end: int) -> int:
    """Return non-whitespace count for [start, end) byte range."""
    if start < 0:
        start = 0
    max_index = int(cumsum.shape[0] - 1)
    if end > max_index:
        end = max_index
    if end <= start:
        return 0
    return int(cumsum[end] - cumsum[start])
