"""AST descent can retain a pending declaration header while packing its body."""

from __future__ import annotations

from omnichunk import Chunker


def test_oversized_body_uses_remaining_header_budget_for_complete_statements():
    source = (
        "def collect(items):\n"
        "    first = normalize(items)\n"
        "    second = apply(first)\n"
        "    third = produce(second)\n"
        "    return third\n"
    )
    chunker = Chunker(
        max_chunk_size=70, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    )
    chunks = chunker.chunk("collect.py", source)
    assert len(chunks) == 2
    assert "def collect(items):\n    first = normalize(items)" in chunks[0].text
    assert "second = apply(first)" in chunks[1].text
    assert "".join(chunk.text for chunk in chunks) == source
    assert all(len(chunk.contextualized_text) <= 70 for chunk in chunks)
    assert [chunk.text for chunk in chunker.stream("collect.py", source)] == [
        chunk.text for chunk in chunks
    ]


def test_carry_preserves_whole_fitting_definition():
    source = "def first():\n    return 1\n\ndef second():\n    return 2\n"
    chunks = Chunker(
        max_chunk_size=35, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    ).chunk("functions.py", source)
    assert len(chunks) == 2
    assert "def first():\n    return 1" in chunks[0].text
    assert "def second():\n    return 2" in chunks[1].text
    assert "".join(chunk.text for chunk in chunks) == source


def test_carry_uses_complete_nonadditive_utf8_counter():
    source = (
        "def görev(öğe):\r\n"
        "    ilk = dönüştür(öğe)\r\n"
        "    ikinci = kaydet(ilk)\r\n"
        "    return ikinci\r\n"
    )

    def count(text):
        return len(text.encode("utf-8")) + 2 + (10 if "ilk" in text and "ikinci" in text else 0)

    chunks = Chunker(
        max_chunk_size=75,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("functions.py", source)
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    for chunk in chunks:
        assert raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= 75


def test_fitting_body_can_pack_complete_statements_with_its_header():
    source = (
        "def collect(items):\n"
        "    first = normalize(items)\n"
        "    second = apply(first)\n"
        "    third = produce(second)\n"
        "    return third\n"
    )
    chunks = Chunker(
        max_chunk_size=100, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    ).chunk("collect.py", source)
    assert len(chunks) == 2
    assert "first = normalize(items)" in chunks[0].text
    assert "second = apply(first)" in chunks[0].text
    assert "third = produce(second)" in chunks[1].text
    assert "".join(chunk.text for chunk in chunks) == source
    assert all(len(chunk.contextualized_text) <= 100 for chunk in chunks)
