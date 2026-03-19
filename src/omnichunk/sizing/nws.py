from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from omnichunk.sizing.rust_accel import (
    NwsBackendStatus,
    maybe_preprocess_nws_cumsum_rust,
    nws_backend_status,
)

_WHITESPACE_BYTES = np.array([9, 10, 11, 12, 13, 32], dtype=np.uint8)
_WHITESPACE_LOOKUP = np.zeros(256, dtype=np.bool_)
_WHITESPACE_LOOKUP[_WHITESPACE_BYTES] = True


def preprocess_nws_cumsum(code: str, *, backend: str | None = None) -> np.ndarray:
    """Build cumulative non-whitespace byte counts for O(1) range queries."""
    rust_result = maybe_preprocess_nws_cumsum_rust(code, backend=backend)
    if rust_result is not None:
        return rust_result

    return preprocess_nws_cumsum_python(code)


def preprocess_nws_cumsum_python(code: str) -> np.ndarray:
    """Pure-Python/Numpy NWS preprocessing used when Rust backend is unavailable."""
    if not code:
        return np.array([0], dtype=np.int64)

    raw = np.frombuffer(code.encode("utf-8"), dtype=np.uint8)
    mask = ~_WHITESPACE_LOOKUP[raw]
    cumsum = np.empty(mask.shape[0] + 1, dtype=np.int64)
    cumsum[0] = 0
    np.cumsum(mask, out=cumsum[1:])
    return cumsum


def get_nws_backend_status(backend: str | None = None) -> NwsBackendStatus:
    """Return active NWS backend details for profiling and diagnostics."""
    return nws_backend_status(backend)


def get_nws_count(cumsum: Sequence[int] | np.ndarray, start: int, end: int) -> int:
    """Return non-whitespace count for [start, end) byte range."""
    if start < 0:
        start = 0
    max_index = len(cumsum) - 1
    if end > max_index:
        end = max_index
    if end <= start:
        return 0
    return int(cumsum[end]) - int(cumsum[start])
