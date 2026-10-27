"""Optional Markdown packing preserves source and structural ownership."""

from __future__ import annotations

import pytest

from omnichunk import Chunker


def test_packing_combines_only_adjacent_prose_in_one_section() -> None:
    source = (
        "# Manual\n\nFirst paragraph.\n\nSecond paragraph.\n\n"
        "| A | B |\n| --- | --- |\n| x | y |\n\n"
        "Third paragraph.\n\nFourth paragraph.\n\n"
        "## Nested\n\nFifth paragraph.\n\nSixth paragraph.\n"
    )
    chunks = Chunker(
        max_chunk_size=500,
        min_chunk_size=100,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy="pack",
    ).chunk("manual.md", source)
    assert len(chunks) == 4
    assert "".join(chunk.text for chunk in chunks) == source
    assert "First paragraph." in chunks[0].text and "Second paragraph." in chunks[0].text
    assert chunks[1].context.section_type == "table"
    assert "Third paragraph." in chunks[2].text and "Fourth paragraph." in chunks[2].text
    assert "Fifth paragraph." in chunks[3].text and "Sixth paragraph." in chunks[3].text
    assert chunks[3].context.heading_hierarchy == ["Manual", "Nested"]


def test_packing_leaves_code_fences_and_lists_separate() -> None:
    source = "First.\n\nSecond.\n\n```text\nhello\n```\n\n- item one\n- item two\n\nLast.\n"
    chunks = Chunker(
        max_chunk_size=500,
        min_chunk_size=200,
        context_mode="none",
        markdown_paragraph_policy="pack",
    ).chunk("manual.md", source)
    assert chunks[0].text == "First.\n\nSecond.\n\n"
    assert chunks[-2].context.section_type == "list"
    assert chunks[-1].context.section_type == "paragraph"
    assert all(chunk.context.section_type == "code_block" for chunk in chunks[1:-2])


@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
def test_packing_fits_measured_payload_and_preserves_unicode_source(unit: str) -> None:
    source = (
        "# Kaynak\r\n\r\n"
        + "\r\n\r\n".join(
            [
                "Belgeyi açın. 😀",
                "İşlemi kaydedin.",
                "資料を確認する。",
                "Son adımı uygulayın.",
            ]
        )
        + "\r\n"
    )

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2 + (5 if "😀" in text and "資料" in text else 0)

    chunker = Chunker(
        max_chunk_size=65,
        min_chunk_size=0,
        size_unit=unit,
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        markdown_paragraph_policy="pack",
    )
    chunks = chunker.chunk("manual.md", source)
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    for chunk in chunks:
        assert raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8") == chunk.text
        value = (
            count(chunk.text)
            if unit == "tokens"
            else (len(chunk.text) if unit == "chars" else sum(not c.isspace() for c in chunk.text))
        )
        assert value <= 65
    assert [chunk.text for chunk in chunker.stream("manual.md", source)] == [
        chunk.text for chunk in chunks
    ]


def test_packing_is_a_validated_per_call_override_and_changes_configuration() -> None:
    source = "First paragraph.\n\nSecond paragraph.\n"
    chunker = Chunker(max_chunk_size=200, context_mode="none")
    separate = chunker.chunk("manual.md", source)
    packed = chunker.chunk("manual.md", source, markdown_paragraph_policy="pack")
    assert len(separate) == 2 and len(packed) == 1
    assert separate[0].config_fingerprint != packed[0].config_fingerprint
    assert len(chunker.chunk("manual.md", source)) == 2
    with pytest.raises(ValueError, match="markdown_paragraph_policy"):
        Chunker(markdown_paragraph_policy="invalid")


def test_plaintext_is_unaffected_by_markdown_packing() -> None:
    source = "First paragraph.\n\nSecond paragraph.\n"
    chunker = Chunker(max_chunk_size=200, context_mode="none")
    normal = chunker.chunk("manual.txt", source)
    packed = chunker.chunk("manual.txt", source, markdown_paragraph_policy="pack")
    assert [(c.text, c.byte_range) for c in normal] == [(c.text, c.byte_range) for c in packed]
