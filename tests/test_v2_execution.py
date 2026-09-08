"""Failure propagation, structured dispatch and isolated export contracts."""

import asyncio
import json
from pathlib import Path

import pytest

from omnichunk import Chunker, PluginRegistry, chunk_directory, chunk_file


def test_batch_reports_errors_in_input_order_and_progress():
    chunker = Chunker()
    inputs = [
        {"filepath": "broken.ipynb", "code": "{"},
        {"filepath": "good.txt", "code": "good source"},
    ]
    progress = []
    results = chunker.batch(inputs, concurrency=2, on_progress=lambda *args: progress.append(args))
    assert results[0].error and not results[0].chunks
    assert results[1].chunks[0].text == "good source"
    assert sorted(p[0] for p in progress) == [1, 2]
    assert all(p[1] == 2 for p in progress)
    assert chunker.batch([]) == []


def test_directory_keeps_valid_results_and_reports_decode_or_parse_failures(tmp_path):
    (tmp_path / "good.txt").write_text("good source")
    (tmp_path / "invalid.txt").write_bytes(b"\xff")
    (tmp_path / "broken.ipynb").write_text("{")
    (tmp_path / "good.rst").write_text("Heading\n=======\n\nText.\n")
    (tmp_path / ".hidden.txt").write_text("hidden")
    (tmp_path / "skip.txt").write_text("excluded")
    results = chunk_directory(str(tmp_path), exclude=["skip.txt"])
    by_name = {Path(r.filepath).name: r for r in results}
    assert set(by_name) == {"good.txt", "invalid.txt", "broken.ipynb", "good.rst"}
    assert by_name["invalid.txt"].error.startswith("Read failed:")
    assert by_name["broken.ipynb"].error
    assert by_name["good.rst"].chunks
    assert Chunker().chunk_directory(str(tmp_path / "broken.ipynb"))[0].error
    assert Chunker().chunk_directory(str(tmp_path / "good.txt"))[0].chunks
    with pytest.raises(FileNotFoundError):
        Chunker().chunk_directory(str(tmp_path / "absent"))
    empty = tmp_path / "empty"
    empty.mkdir()
    assert Chunker().chunk_directory(str(empty)) == []


def test_directory_and_async_batch_report_budget_errors(tmp_path):
    (tmp_path / "source.txt").write_text("a long source " * 10)
    chunker = Chunker(max_chunk_size=5, overflow_policy="error")
    results = chunker.chunk_directory(str(tmp_path))
    assert results[0].error and not results[0].chunks

    async def run():
        return await Chunker().abatch(
            [
                {"filepath": "good.txt", "code": "good"},
                {"filepath": "bad.txt", "code": "bad", "unknown_option": True},
            ]
        )

    results = asyncio.run(run())
    assert results[0].chunks[0].text == "good"
    assert results[1].error and not results[1].chunks


@pytest.mark.parametrize("suffix", [".pdf", ".docx"])
def test_binary_file_stream_uses_canonical_loader(tmp_path, monkeypatch, suffix):
    import importlib

    from omnichunk.formats.rst import load_rst

    module = importlib.import_module("omnichunk.chunker")
    loader = "load_pdf_bytes" if suffix == ".pdf" else "load_docx_bytes"
    observed = []

    def extract(data):
        observed.append(data)
        return load_rst("Türkçe source\n")

    monkeypatch.setattr(module, loader, extract)
    path = tmp_path / ("source" + suffix)
    path.write_bytes(b"binary container")
    chunker = Chunker(coverage_policy="lossless")
    chunks = list(chunker.stream_file(str(path)))
    assert observed == [b"binary container"]
    assert "".join(c.text for c in chunks) == "Türkçe source\n"
    assert all(c.total_chunks == -1 and c.source.normalization == "extracted" for c in chunks)
    with pytest.raises(ValueError, match="chunk_file"):
        chunker.chunk(str(path), "binary container")


def test_file_decoding_preserves_canonical_source_and_read_errors(tmp_path):
    path = tmp_path / "latin.txt"
    path.write_bytes("café\r\n".encode("latin-1"))
    result = chunk_file(str(path), encoding="latin-1", coverage_policy="lossless")
    assert result[0].text == "café\r\n"
    assert result[0].source.normalization == "decoded:latin-1"
    assert result[0].byte_range.end == len("café\r\n".encode())
    with pytest.raises(FileNotFoundError):
        Chunker().chunk_file(str(tmp_path / "absent.txt"))
    with pytest.raises(UnicodeDecodeError):
        list(Chunker().stream_upsert(str(path), embed_fn=lambda texts: [[1.0] for _ in texts]))


def test_async_stream_propagates_producer_failure_and_validates_capacity():
    async def run():
        with pytest.raises(ValueError):
            _ = [c async for c in Chunker().astream("x.txt", "text", buffer_size=0)]
        with pytest.raises(TypeError, match="Unknown"):
            _ = [c async for c in Chunker().astream("x.txt", "text", missing=True)]
        result = [c async for c in Chunker().astream("x.txt", "text", buffer_size=1)]
        assert result[0].text == "text"

    asyncio.run(run())


def test_formatter_isolation_and_missing_registry_errors():
    registry = PluginRegistry()
    registry.register_formatter("text", lambda chunks: "|".join(c.text for c in chunks))
    chunker = Chunker(registry=registry)
    chunks = chunker.chunk("x.txt", "source")
    assert chunker.format(chunks, "text") == "source"
    with pytest.raises(ValueError, match="formatter"):
        Chunker(registry=PluginRegistry()).format(chunks, "text")
    with pytest.raises(TypeError, match="registry"):
        Chunker(registry={})


def test_notebook_file_keeps_cell_coordinates(tmp_path):
    path = tmp_path / "source.ipynb"
    path.write_text(
        json.dumps({"cells": [{"cell_type": "markdown", "source": ["# Heading\n", "Text."]}]})
    )
    chunks = Chunker().chunk_file(str(path))
    assert chunks and all(c.source.format_name == "ipynb" for c in chunks)
    assert all(c.context.format_metadata["cell"] == 0 for c in chunks)
