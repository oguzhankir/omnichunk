from __future__ import annotations

from types import SimpleNamespace

import pytest

from benchmarks.retrieval import tokenization
from benchmarks.retrieval.adapters import Passage, split_document
from benchmarks.retrieval.ranking import select_budget


def fake_hf(monkeypatch, directory):
    class Encoder:
        def encode(self, text, *, add_special_tokens, truncation):
            assert add_special_tokens is True and truncation is False
            return [0] * (len(text) + 2)

    def load(path, **kwargs):
        assert path == str(directory.resolve())
        assert kwargs == {"local_files_only": True, "trust_remote_code": False}
        return Encoder()

    monkeypatch.setattr(
        tokenization,
        "import_module",
        lambda name: SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=load)),
    )


def test_full_model_counter_bounds_chunks_and_complete_retrieved_context(tmp_path, monkeypatch):
    fake_hf(monkeypatch, tmp_path)
    count = tokenization.benchmark_counter("tokens", str(tmp_path), include_special_tokens=True)
    assert count("abc") == 5 and count("") == 2
    chunks = split_document("fixed", "doc", "doc.txt", "abcdefgh", 5, count, "tokens")
    assert [chunk.text for chunk in chunks] == ["abc", "def", "gh"]
    assert all(count(chunk.text) <= 5 for chunk in chunks)
    a, b = [Passage(text, "doc", 0, 2, text) for text in ("aa", "bb")]
    ranked = [(a, 1.0), (b, 0.5)]
    assert select_budget(ranked, 7, count) == ranked[:1]
    assert select_budget(ranked, 8, count) == ranked


def test_default_content_counter_retains_existing_behavior(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(tokenization, "make_token_counter", lambda name: seen.append(name) or len)
    monkeypatch.setattr(tokenization, "import_module", lambda _: pytest.fail("unexpected HF load"))
    assert tokenization.benchmark_counter("chars", "unused") is len
    assert tokenization.benchmark_counter("tokens", "existing")("abc") == 3
    assert seen == ["existing"]


@pytest.mark.parametrize(
    "unit,name", [("chars", "."), ("tokens", "cl100k_base"), ("tokens", "approximate")]
)
def test_special_token_mode_rejects_nonlocal_or_character_counters(unit, name):
    with pytest.raises(ValueError):
        tokenization.benchmark_counter(unit, name, include_special_tokens=True)


@pytest.mark.parametrize("ids", ["ids", [True], [-1], [1.5]])
def test_invalid_hf_output_is_not_silently_counted(tmp_path, monkeypatch, ids):
    encoder = SimpleNamespace(encode=lambda *args, **kwargs: ids)
    monkeypatch.setattr(
        tokenization,
        "import_module",
        lambda _: SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: encoder)
        ),
    )
    count = tokenization.benchmark_counter("tokens", str(tmp_path), include_special_tokens=True)
    with pytest.raises(ValueError, match="token IDs"):
        count("text")
