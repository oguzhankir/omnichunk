from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from omnichunk import Chunker


@pytest.mark.parametrize(
    "options",
    [
        {"max_size": 3},
        {"size_unit": "bytes"},
        {"max_chunk_size": 0},
        {"overlap": -1},
        {"_precomputed_text_index": object()},
        {"preserve_comments": False},
        {"semantic_threshold_k": 2},
    ],
)
def test_invalid_or_unsupported_options_fail_loud(options):
    with pytest.raises((ValueError, TypeError)):
        Chunker(**options)


def test_exact_token_mode_requires_explicit_counter():
    with pytest.raises(ValueError, match="tokenizer"):
        Chunker(size_unit="tokens")


def test_configuration_is_immutable():
    chunker = Chunker(size_unit="chars")
    with pytest.raises(FrozenInstanceError):
        chunker._defaults.max_chunk_size = 2


@pytest.mark.parametrize(
    "filepath,text",
    [
        ("sample.py", "".join(f"x{i} = {i}\n" for i in range(100))),
        ("doc.md", "# Başlık\n\n" + "世界 merhaba. " * 40),
        ("data.json", '{"name": "' + "你好" * 60 + '"}'),
    ],
)
def test_payload_budget_source_and_stream_contract(filepath, text):
    chunker = Chunker(max_chunk_size=40, min_chunk_size=1, size_unit="chars")
    chunks = chunker.chunk(filepath, text)
    stream = list(chunker.stream(filepath, text))
    assert chunks and all(len(c.contextualized_text) <= 40 for c in chunks)
    assert [c.text for c in chunks] == [c.text for c in stream]
    assert all(c.total_chunks == -1 for c in stream)
    raw = text.encode()
    for c in chunks:
        assert raw[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert c.source.source_id == filepath
        assert c.config_fingerprint
        assert c.metadata["budget"]["size"] <= 40


def test_lossless_keeps_whitespace_and_trailing_source():
    for text in ["   \n\t", " \nhello\n\n  ", "", "\u2003\n"]:
        chunks = Chunker(max_chunk_size=4, min_chunk_size=1, coverage_policy="lossless").chunk(
            "x.txt", text
        )
        assert "".join(c.text for c in chunks) == text


def test_overlap_matches_stream_and_respects_payload_limit():
    text = "hello world. " * 80
    chunker = Chunker(max_chunk_size=50, min_chunk_size=1, overlap=0.2)
    chunks = chunker.chunk("x.txt", text)
    stream = list(chunker.stream("x.txt", text))
    assert [c.text for c in chunks] == [c.text for c in stream]
    assert all(len(c.contextualized_text) <= 50 for c in chunks)
    assert any(a.byte_range.end > b.byte_range.start for a, b in zip(chunks, chunks[1:]))


def test_overflow_error_and_preserve_are_explicit():
    text = "supercalifragilisticexpialidocious"
    with pytest.raises(Exception, match="exceeds"):
        Chunker(max_chunk_size=4, overflow_policy="error").chunk("x.txt", text)
    chunks = Chunker(max_chunk_size=4, overflow_policy="preserve").chunk("x.txt", text)
    assert chunks[0].metadata["budget"]["overflow"] > 0
    assert chunks[0].metadata["overflow_reason"]


def test_context_budget_error_is_actionable():
    with pytest.raises(Exception, match="Context"):
        Chunker(max_chunk_size=10, context_overflow="error").chunk("a-very-long-path.txt", "hi")


def test_manifest_accounts_for_skipped_whitespace():
    result = Chunker().chunk_with_manifest("x.txt", " \n\t")
    assert not result.chunks
    assert [(r.start, r.end) for r in result.skipped_ranges] == [(0, 3)]
    full = Chunker(coverage_policy="lossless").chunk_with_manifest("x.txt", " \n\t")
    assert not full.skipped_ranges
    with pytest.raises(ValueError, match="canonical"):
        Chunker().chunk_with_manifest("x.ipynb", "{}")


def test_instance_plugin_registries_are_isolated():
    from omnichunk import PluginRegistry

    calls = []
    first, second = PluginRegistry(), PluginRegistry()
    first.register_parser("python", lambda fp, text: calls.append("first"))
    second.register_parser("python", lambda fp, text: calls.append("second"))
    a, b = Chunker(registry=first), Chunker(registry=second)
    a.chunk("a.py", "def f(): pass")
    b.chunk("a.py", "def f(): pass")
    assert calls == ["first", "second"]
    with pytest.raises(ValueError, match="already"):
        first.register_parser("python", lambda fp, text: None)
    first.register_formatter("count", lambda chunks: str(len(chunks)))
    with pytest.raises(ValueError, match="already"):
        first.register_formatter("count", lambda chunks: "")
    assert not second.formatters


def test_astream_close_cancels_bounded_producer(monkeypatch):
    import asyncio
    from dataclasses import replace
    from threading import Event

    one = Chunker().chunk("a.txt", "hello")[0]
    closed = Event()
    produced = []

    def source(self, filepath, content, **kwargs):
        try:
            for i in range(100000):
                produced.append(i)
                yield replace(one, index=i)
        finally:
            closed.set()

    monkeypatch.setattr(Chunker, "stream", source)

    async def run():
        stream = Chunker().astream("a.txt", "hello", buffer_size=2)
        await anext(stream)
        await stream.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=2))
    assert closed.is_set()
    assert len(produced) < 10


def test_stream_upsert_does_not_collect_file_chunks(tmp_path, monkeypatch):
    path = tmp_path / "source.txt"
    path.write_text("hello " * 100)

    def forbidden(*args, **kwargs):
        raise AssertionError("should use stream_file")

    monkeypatch.setattr(Chunker, "chunk_file", forbidden)
    batches = list(
        Chunker(max_chunk_size=20).stream_upsert(
            str(path), batch_size=2, embed_fn=lambda texts: [[1.0] for _ in texts]
        )
    )
    assert batches and all(len(batch.rows) <= 2 for batch in batches)


def test_explicit_token_counter_budget_counts_rendered_payload():
    def counter(text):
        return len(text.encode("utf-8"))

    chunks = Chunker(max_chunk_size=12, tokenizer=counter, size_unit="tokens").chunk(
        "x.txt", "你好世界 " * 15
    )
    assert all(counter(c.contextualized_text) <= 12 for c in chunks)
    assert all(c.token_count == counter(c.text) for c in chunks)
    with pytest.raises(Exception, match="single Unicode"):
        Chunker(max_chunk_size=1, tokenizer=counter, size_unit="tokens").chunk("x.txt", "你")


def test_evaluation_detects_missing_source_and_does_not_double_count_overlap():
    from dataclasses import replace

    from omnichunk import ByteRange, evaluate_chunks

    text = "你好 world. trailing source."
    chunk = Chunker().chunk("x.txt", text)[0]
    prefix = text[:8]
    part = replace(chunk, text=prefix, byte_range=ByteRange(0, len(prefix.encode())))
    report = evaluate_chunks([part, part], text, metrics=["coverage"])
    assert report.aggregate["coverage"] == len(prefix.encode()) / len(text.encode())
    assert evaluate_chunks([chunk], text, metrics=["coverage"]).aggregate["coverage"] == 1.0
    with pytest.raises(ValueError, match="Unknown"):
        evaluate_chunks([chunk], text, metrics=["missing"])


def test_hierarchy_preserves_source_and_measures_parent_tokens():
    # A non-additive counter catches summing child token counts for parents.
    def counter(text):
        return len(text) + (7 if len(text) > 20 else 0)

    tree = Chunker(tokenizer=counter, size_unit="tokens").hierarchical_chunk(
        "x.txt", "sentence here. " * 15, levels=[20, 45, 90]
    )
    for node in tree.nodes:
        c = node.chunk
        assert c.source is not None
        assert c.token_count == counter(c.text)
        assert c.token_count <= [20, 45, 90][node.level]
        assert c.metadata["budget"]["size"] == counter(c.contextualized_text)
    with pytest.raises(ValueError, match="non-overlapping"):
        Chunker(overlap=0.2).hierarchical_chunk("x.txt", "hello " * 30, levels=[20, 40])
