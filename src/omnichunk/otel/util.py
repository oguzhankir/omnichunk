from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any


def _span_set(span: object | None, key: str, value: Any) -> None:
    if span is None:
        return
    setter = getattr(span, "set_attribute", None)
    if setter is None:
        return
    with suppress(Exception):
        setter(key, value)


# Public alias — preferred in new code.
span_set = _span_set


def record_span_error(span: object | None, exc: BaseException) -> None:
    """Record an exception event and set ERROR status on a span (duck-typed)."""
    if span is None:
        return
    with suppress(Exception):
        record = getattr(span, "record_exception", None)
        if callable(record):
            record(exc)
    with suppress(Exception):
        set_status = getattr(span, "set_status", None)
        if not callable(set_status):
            return
        try:
            from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

            set_status(Status(StatusCode.ERROR, str(exc)))
        except ImportError:
            pass


@contextmanager
def maybe_span(tracer: object | None, name: str, **initial_attrs: Any) -> Iterator[Any]:
    """OpenTelemetry span context manager; no-op when ``tracer`` is None."""
    if tracer is None:
        yield None
        return
    enter = getattr(tracer, "start_as_current_span", None)
    if enter is None:
        yield None
        return
    with enter(name) as span:
        for k, v in initial_attrs.items():
            _span_set(span, k, v)
        yield span


def finalize_chunk_file_span(
    span: object | None,
    *,
    chunk_count: int,
    t0: float,
    error: str | None = None,
) -> None:
    """Set duration and counts on an active chunk_file span."""
    dur = time.perf_counter() - t0
    _span_set(span, "omnichunk.chunking_duration_ms", round(dur * 1000.0, 3))
    _span_set(span, "omnichunk.chunk_count", chunk_count)
    if error:
        _span_set(span, "omnichunk.parse_errors", error[:2000])
