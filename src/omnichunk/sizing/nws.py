from __future__ import annotations

from collections.abc import Sequence
from itertools import accumulate
from typing import Any

from omnichunk.sizing.rust_accel import (
    NwsBackendStatus,
    maybe_preprocess_nws_cumsum_rust,
    nws_backend_status,
)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def preprocess_nws_cumsum(code: str, *, backend: str | None = None) -> Any:
    """Build cumulative non-whitespace byte counts in O(N), with optional NumPy."""
    rust_result = maybe_preprocess_nws_cumsum_rust(code, backend=backend)
    if rust_result is not None:
        return rust_result
    return preprocess_nws_cumsum_python(code)


def preprocess_nws_cumsum_python(code: str) -> Any:
    raw = code.encode("utf-8")
    if np is None:
        return list(accumulate((b not in b" \t\n\r\v\f" for b in raw), initial=0))
    lookup = np.ones(256, dtype=np.bool_)
    lookup[[9, 10, 11, 12, 13, 32]] = False
    mask = lookup[np.frombuffer(raw, dtype=np.uint8)]
    result = np.empty(len(raw) + 1, dtype=np.int64)
    result[0] = 0
    np.cumsum(mask, out=result[1:])
    return result


def slice_nws_cumsum(cumsum: Any, start: int, end: int) -> Any:
    """Rebase a cumulative byte index for [start,end), supporting stdlib arrays."""
    if np is not None and isinstance(cumsum, np.ndarray):
        return cumsum[start : end + 1] - cumsum[start]
    base = int(cumsum[start])
    return [int(cumsum[i]) - base for i in range(start, end + 1)]


def get_nws_backend_status(backend: str | None = None) -> NwsBackendStatus:
    return nws_backend_status(backend)


def get_nws_count(cumsum: Sequence[int] | Any, start: int, end: int) -> int:
    start = max(0, start)
    end = min(end, len(cumsum) - 1)
    return int(cumsum[end]) - int(cumsum[start]) if end > start else 0
