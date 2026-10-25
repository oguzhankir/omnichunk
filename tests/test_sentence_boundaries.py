from __future__ import annotations

import numpy as np
import pytest

from omnichunk import Chunker, split_sentences


@pytest.mark.parametrize(
    "parts",
    [
        ["İlk cümle. ", "İkinci cümle! ", "Şimdi üçüncü? ", "Üçü de korunur."],
        ["First sentence. ", "Également en français. ", "Überall lesbar."],
        ["最初の文です。", "次の文です！", "最後の文です？"],
        ["这是第一句。", "这是第二句！", "这是第三句？"],
        ["Mixed text. ", "日本語でも分割。", "Back to English."],
        ["He said “Done.” ", "Next sentence."],
        ["『完了。』", "「次の作業！」 ", "最後。"],
        ["Ready?! ", "(Another sentence.) ", '"Final sentence."'],
        ["First paragraph\r\n\t \r\n", "lowercase paragraph\r\n\r\n", "last"],
        ["First.\r\n\r\n", "lowercase after a paragraph break."],
        ["A combining mark e\u0301. ", "İkinci😀. ", "終わり。"],
        ["Step complete. ", "2 records remain."],
    ],
)
def test_unicode_sentence_boundaries_preserve_source_and_character_offsets(parts):
    text = "".join(parts)

    actual = split_sentences(text)

    assert [sentence for sentence, _, _ in actual] == parts
    assert "".join(sentence for sentence, _, _ in actual) == text
    assert actual[0][1] == 0
    assert actual[-1][2] == len(text)
    assert all(text[start:end] == sentence for sentence, start, end in actual)
    assert all(left[2] == right[1] for left, right in zip(actual, actual[1:]))


@pytest.mark.parametrize(
    "text",
    [
        "Version 2.1.4 uses 3.14 units at https://example.org/v1.2.",
        "module.Class.method() must remain one identifier.",
        "A continuation, e.g. this lowercase example, stays together.",
        "First sentence. lowercase continuation.",
        "資料😀" * 20,
        "Single final sentence.   \r\n",
        " \t\r\n",
    ],
)
def test_conservative_period_boundaries_and_delimiter_free_text(text):
    assert split_sentences(text) == [(text, 0, len(text))]


@pytest.mark.parametrize(
    "sentences",
    [
        ["İlk cümle. ", "İkinci cümle. ", "Şimdi bitti."],
        ["最初の文です。", "次の文です。", "最後の文です。"],
    ],
)
def test_semantic_chunking_uses_unicode_sentences_and_exact_utf8_ranges(sentences):
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.eye(len(texts))

    text = "".join(sentences)
    chunks = Chunker(
        max_chunk_size=256,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
        semantic=True,
        semantic_embed_fn=embed,
        semantic_window=1,
        semantic_threshold=0.5,
    ).chunk("notes.txt", text)

    assert calls == [sentences]
    assert [chunk.text for chunk in chunks] == sentences
    raw = text.encode("utf-8")
    assert all(raw[c.byte_range.start : c.byte_range.end].decode("utf-8") == c.text for c in chunks)
