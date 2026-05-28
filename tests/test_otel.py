from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from omnichunk import Chunker
from omnichunk.otel.util import maybe_span

# ---------------------------------------------------------------------------
# Lightweight fake tracer (no opentelemetry-sdk dependency)
# ---------------------------------------------------------------------------


class _FakeSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attrs: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attrs[key] = value


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_as_current_span(self, name: str):
        span = _FakeSpan(name)
        self.spans.append(span)

        class CM:
            def __enter__(self_inner) -> _FakeSpan:
                return span

            def __exit__(self_inner, *exc: object) -> None:
                return None

        return CM()

    def span_by_name(self, name: str) -> _FakeSpan | None:
        return next((s for s in self.spans if s.name == name), None)


# ---------------------------------------------------------------------------
# InMemorySpanExporter helpers (opentelemetry-sdk required)
# ---------------------------------------------------------------------------


def _make_sdk_tracer():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test.omnichunk"), exporter


# ---------------------------------------------------------------------------
# Legacy fake-tracer tests (kept for fast / dependency-free coverage)
# ---------------------------------------------------------------------------


def test_chunk_file_otel_span_attributes(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    ft = _FakeTracer()
    c = Chunker(otel_tracer=ft)
    c.chunk_file(str(f))
    assert ft.spans
    root = ft.span_by_name("omnichunk.chunk_file")
    assert root is not None
    assert root.attrs.get("omnichunk.chunk_count", 0) >= 1
    assert "omnichunk.chunking_duration_ms" in root.attrs


def test_chunker_no_tracer_no_crash(tmp_path: Path) -> None:
    f = tmp_path / "b.py"
    f.write_text("y = 2\n", encoding="utf-8")
    c = Chunker()
    chunks = c.chunk_file(str(f))
    assert chunks


# ---------------------------------------------------------------------------
# (a) Root span omnichunk.chunk_file is created when otel_tracer is set
# ---------------------------------------------------------------------------


def test_otel_root_span_created(tmp_path: Path) -> None:
    tracer, exporter = _make_sdk_tracer()
    f = tmp_path / "root.py"
    f.write_text("x = 1\n", encoding="utf-8")
    Chunker(otel_tracer=tracer).chunk_file(str(f))

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "omnichunk.chunk_file" in names, f"root span missing; got: {names}"
    root = next(s for s in spans if s.name == "omnichunk.chunk_file")
    assert root.parent is None, "chunk_file span must be the root (no parent)"


# ---------------------------------------------------------------------------
# (b) Child spans for engine routing phase
# ---------------------------------------------------------------------------


def test_otel_child_span_engine_route(tmp_path: Path) -> None:
    tracer, exporter = _make_sdk_tracer()
    f = tmp_path / "child.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    Chunker(otel_tracer=tracer).chunk_file(str(f))

    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "omnichunk.engine.route" in names, f"child span missing; got: {names}"

    root = next(s for s in spans if s.name == "omnichunk.chunk_file")
    child = next(s for s in spans if s.name == "omnichunk.engine.route")
    assert child.parent is not None, "engine.route span must have a parent"
    assert child.parent.span_id == root.context.span_id, (
        "engine.route span must be a child of chunk_file span"
    )


# ---------------------------------------------------------------------------
# (c) Span attributes: filepath, engine_name, chunk_count, size_unit
# ---------------------------------------------------------------------------


def test_otel_span_attributes_complete(tmp_path: Path) -> None:
    tracer, exporter = _make_sdk_tracer()
    f = tmp_path / "attrs.py"
    f.write_text(
        "import os\n\nclass MyClass:\n    def method(self):\n        return os.getcwd()\n",
        encoding="utf-8",
    )
    Chunker(otel_tracer=tracer, size_unit="chars", max_chunk_size=300).chunk_file(str(f))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "omnichunk.chunk_file")
    child = next(s for s in spans if s.name == "omnichunk.engine.route")

    # filepath on both spans
    assert "filepath" in root.attributes, "root span must have filepath"
    assert str(f.resolve()) in root.attributes["filepath"]
    assert "filepath" in child.attributes, "child span must have filepath"

    # engine_name on child
    assert "omnichunk.engine_name" in child.attributes, "child span must have engine_name"
    assert child.attributes["omnichunk.engine_name"] == "code"

    # chunk_count on root
    assert "omnichunk.chunk_count" in root.attributes
    assert root.attributes["omnichunk.chunk_count"] >= 1

    # size_unit on root and child
    assert root.attributes.get("omnichunk.size_unit") == "chars"
    assert child.attributes.get("omnichunk.size_unit") == "chars"


# ---------------------------------------------------------------------------
# (d) When otel_tracer=None (default): no spans, negligible overhead
# ---------------------------------------------------------------------------


def test_otel_no_tracer_no_spans(tmp_path: Path) -> None:
    f = tmp_path / "notrace.py"
    f.write_text("z = 99\n", encoding="utf-8")

    # Default: tracer is None → no OTel calls, code must not error
    chunks_no_tracer = Chunker().chunk_file(str(f))
    chunks_explicit_none = Chunker(otel_tracer=None).chunk_file(str(f))
    assert chunks_no_tracer
    assert [c.text for c in chunks_no_tracer] == [c.text for c in chunks_explicit_none]


def test_otel_no_tracer_overhead() -> None:
    """maybe_span(None, ...) must be a near-zero-cost no-op."""
    iterations = 10_000
    t0 = time.perf_counter()
    for _ in range(iterations):
        with maybe_span(None, "test.span", filepath="x.py", size_unit="tokens") as s:
            assert s is None
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, (
        f"maybe_span(None) overhead too high: {elapsed:.3f}s for {iterations} iters"
    )


# ---------------------------------------------------------------------------
# (e) Span errors recorded when parser raises an exception
# ---------------------------------------------------------------------------


def test_otel_error_recorded_on_parser_exception(tmp_path: Path) -> None:
    from opentelemetry.trace import StatusCode

    tracer, exporter = _make_sdk_tracer()
    f = tmp_path / "boom.py"
    f.write_text("x = 1\n", encoding="utf-8")

    c = Chunker(otel_tracer=tracer)
    with (
        patch("omnichunk.chunker.route_content", side_effect=RuntimeError("parse exploded")),
        pytest.raises(RuntimeError, match="parse exploded"),
    ):
        c.chunk_file(str(f))

    spans = exporter.get_finished_spans()
    assert spans, "spans must be emitted even when an exception is raised"

    root = next((s for s in spans if s.name == "omnichunk.chunk_file"), None)
    assert root is not None, "chunk_file root span must exist"

    # Status must be ERROR
    assert root.status.status_code == StatusCode.ERROR, (
        f"expected ERROR status, got {root.status.status_code}"
    )

    # Error string must be recorded as attribute
    assert root.attributes.get("omnichunk.parse_errors") == "parse exploded"

    # Exception event must be present (from record_exception call)
    exc_events = [ev for ev in root.events if ev.name == "exception"]
    assert exc_events, "root span must have an exception event"
    assert any("parse exploded" in str(ev.attributes) for ev in exc_events)
