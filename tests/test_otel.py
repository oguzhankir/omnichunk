from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker


class _FakeSpan:
    def __init__(self) -> None:
        self.attrs: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attrs[key] = value


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_as_current_span(self, name: str):
        span = _FakeSpan()
        self.spans.append(span)

        class CM:
            def __enter__(self_inner) -> _FakeSpan:
                return span

            def __exit__(self_inner, *exc: object) -> None:
                return None

        return CM()


def test_chunk_file_otel_span_attributes(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    ft = _FakeTracer()
    c = Chunker(otel_tracer=ft)
    c.chunk_file(str(f))
    assert ft.spans
    span = ft.spans[-1]
    assert "omnichunk.chunk_count" in span.attrs
    assert span.attrs["omnichunk.chunk_count"] >= 1
    assert "omnichunk.chunking_duration_ms" in span.attrs


def test_chunker_no_tracer_no_crash(tmp_path: Path) -> None:
    f = tmp_path / "b.py"
    f.write_text("y = 2\n", encoding="utf-8")
    c = Chunker()
    chunks = c.chunk_file(str(f))
    assert chunks
