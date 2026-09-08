from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import run_comparisons as comparisons  # noqa: E402
import run_gutenberg as gutenberg  # noqa: E402
from run_benchmarks import Scenario  # noqa: E402


class ByteTokenizer:
    def encode(self, text: str, **kwargs: object) -> list[int]:
        return list(text.encode("utf-8"))


@pytest.mark.parametrize("unit", ["chars", "tokens"])
@pytest.mark.parametrize("tool", ["semchunk", "langchain_recursive", "semantic_text_splitter"])
def test_comparators_use_identical_budget_and_counter(
    monkeypatch: pytest.MonkeyPatch, unit: str, tool: str
) -> None:
    observed: dict[str, object] = {}

    class Splitter:
        def __init__(self, capacity: int | None = None, **kwargs: object) -> None:
            observed["budget"] = capacity or kwargs.get("chunk_size")
            observed["counter"] = kwargs.get("length_function", len)
            observed["overlap"] = kwargs.get("chunk_overlap", kwargs.get("overlap", 0))

        @classmethod
        def from_callback(cls, counter: object, capacity: int, **kwargs: object) -> Splitter:
            splitter = cls(capacity, **kwargs)
            observed["counter"] = counter
            return splitter

        def chunks(self, text: str) -> list[str]:
            return [text]

        split_text = chunks

    def chunkerify(counter: object, chunk_size: int) -> object:
        observed.update(counter=counter, budget=chunk_size, overlap=0)
        return lambda text, **kwargs: [text]

    modules = {
        "semchunk": SimpleNamespace(chunkerify=chunkerify),
        "langchain_text_splitters": SimpleNamespace(RecursiveCharacterTextSplitter=Splitter),
        "semantic_text_splitter": SimpleNamespace(TextSplitter=Splitter, MarkdownSplitter=Splitter),
    }
    monkeypatch.setattr(comparisons, "_optional_import", modules.get)
    monkeypatch.setitem(
        sys.modules, "tiktoken", SimpleNamespace(get_encoding=lambda _: ByteTokenizer())
    )
    scenario = Scenario("fixture", Path("fixture.txt"), 48, 1, unit)
    count = getattr(comparisons, f"_run_{tool}")("Türkçe 你好", scenario, scenario.path)
    assert count == 1
    assert observed["budget"] == 48
    assert observed["overlap"] == 0
    counter = observed["counter"]
    assert callable(counter)
    sample = "Türkçe many short words 你好"
    assert counter(sample) == (len(sample) if unit == "chars" else len(sample.encode()))


def test_omnichunk_comparison_omits_derived_context(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class Chunker:
        def chunk(self, filepath: str, text: str, **options: object) -> list[object]:
            observed.update(options)
            return [SimpleNamespace(contextualized_text=text)]

    monkeypatch.setattr(comparisons, "Chunker", Chunker)
    scenario = Scenario("fixture", Path("fixture.py"), 48, 1)
    assert comparisons._run_omnichunk("x = 1", scenario, scenario.path) == 1
    assert observed["context_mode"] == "none"
    assert observed["overlap"] == 0


def test_overflowing_comparator_output_is_not_valid_timing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def chunkerify(counter: object, chunk_size: int) -> object:
        return lambda text, **kwargs: [text]

    monkeypatch.setattr(
        comparisons, "_optional_import", lambda name: SimpleNamespace(chunkerify=chunkerify)
    )
    path = tmp_path / "fixture.txt"
    path.write_text("unbroken_text_larger_than_budget", encoding="utf-8")
    scenario = Scenario("fixture", path, 8, 1)
    result = comparisons._benchmark_runner("semchunk", comparisons._run_semchunk, scenario)
    assert result.status == "error"
    assert "budget" in result.detail.lower()


def test_astchunk_without_verified_units_is_excluded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        comparisons,
        "_optional_import",
        lambda name: SimpleNamespace(chunk=lambda text, **_: [text]),
    )
    path = tmp_path / "fixture.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = comparisons._benchmark_runner(
        "astchunk", comparisons._run_astchunk, Scenario("fixture", path, 48, 1)
    )
    assert result.status == "unavailable"
    assert "budget" in result.detail.lower()


def test_gutenberg_measures_output_tokens_and_utf8_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class Chunker:
        def chunk(self, filepath: str, text: str, **options: object) -> list[object]:
            observed.update(options)
            return [SimpleNamespace(contextualized_text="é" * 300)]

    monkeypatch.setattr(gutenberg, "Chunker", Chunker)
    monkeypatch.setitem(
        sys.modules,
        "tiktoken",
        SimpleNamespace(
            get_encoding=lambda _: ByteTokenizer(), encoding_for_model=lambda _: ByteTokenizer()
        ),
    )
    result = gutenberg._run_omnichunk(["é"])
    assert observed["tokenizer"] == "cl100k_base"
    assert observed["context_mode"] == "none"
    assert observed["overlap"] == 0
    assert result.total_bytes == 2
    assert result.total_tokens == 2
    assert result.output_tokens == result.avg_chunk_tokens == 600
    assert result.max_chunk_tokens == 600
    assert result.overflow_chunks == 1
    assert result.status == "overflow"


def test_gutenberg_semantic_splitter_requires_exact_token_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class Splitter:
        @classmethod
        def from_callback(cls, callback: object, capacity: int, **kwargs: object) -> object:
            observed.update(callback=callback, capacity=capacity, **kwargs)
            return SimpleNamespace(chunks=lambda text: [text])

    monkeypatch.setattr(
        gutenberg, "_optional_import", lambda name: SimpleNamespace(TextSplitter=Splitter)
    )
    monkeypatch.setitem(
        sys.modules, "tiktoken", SimpleNamespace(get_encoding=lambda _: ByteTokenizer())
    )
    result = gutenberg._run_semantic_text_splitter(["Türkçe 你好"])
    assert observed["capacity"] == 512
    assert observed["overlap"] == 0
    assert callable(observed["callback"])
    assert observed["callback"]("é") == 2
    assert result.status == "ok"


def test_partial_scenarios_cannot_create_a_speed_comparison(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenarios = [Scenario(name, tmp_path / f"{name}.txt", 48, 1) for name in ("a", "b")]
    monkeypatch.setattr(comparisons, "_comparison_scenarios", lambda _: (scenarios, None))

    def result(tool: str, runner: object, scenario: Scenario) -> comparisons.ToolResult:
        status = "ok"
        if tool == "semchunk" and scenario.name == "b":
            status = "unavailable"
        seconds = 0.001 if tool == "semchunk" else 1.0
        return comparisons.ToolResult(tool, scenario.name, 1024, 1, seconds, 1.0, status)

    monkeypatch.setattr(comparisons, "_benchmark_runner", result)
    destination = tmp_path / "comparison.json"
    assert comparisons.run(["--no-table", "--save", str(destination)]) == 0
    payload = json.loads(destination.read_text())
    assert payload["winner"] == ""
    assert "omnichunk_vs_semchunk" not in payload["speedup"]
    assert payload["tools"]["semchunk"]["status"] == "partial"
    assert payload["configuration"]["overlap"] == 0
