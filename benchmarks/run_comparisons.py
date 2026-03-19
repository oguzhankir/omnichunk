from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from time import perf_counter
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from omnichunk import Chunker

from run_benchmarks import SCENARIOS, Scenario


@dataclass(frozen=True)
class ToolResult:
    tool: str
    scenario: str
    data_bytes: int
    chunks: int
    seconds: float
    mbps: float
    status: str
    detail: str = ""


def _optional_import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _run_omnichunk(text: str, scenario: Scenario, filepath: Path) -> int:
    chunker = Chunker()
    chunks = chunker.chunk(
        str(filepath),
        text,
        max_chunk_size=scenario.max_chunk_size,
        min_chunk_size=scenario.min_chunk_size,
        size_unit=scenario.size_unit,
    )
    return len(chunks)


def _run_langchain_recursive(text: str, scenario: Scenario, filepath: Path) -> int:
    splitter_cls = None

    module = _optional_import("langchain_text_splitters")
    if module is not None:
        splitter_cls = getattr(module, "RecursiveCharacterTextSplitter", None)

    if splitter_cls is None:
        module = _optional_import("langchain.text_splitter")
        if module is not None:
            splitter_cls = getattr(module, "RecursiveCharacterTextSplitter", None)

    if splitter_cls is None:
        raise ImportError("langchain RecursiveCharacterTextSplitter is unavailable")

    splitter = splitter_cls(
        chunk_size=scenario.max_chunk_size,
        chunk_overlap=0,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_text(text)
    return len(chunks)


def _run_semantic_text_splitter(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("semantic_text_splitter")
    if module is None:
        raise ImportError("semantic_text_splitter is unavailable")

    suffix = filepath.suffix.lower()
    if suffix in {".md", ".markdown"}:
        splitter = module.MarkdownSplitter(scenario.max_chunk_size)
    else:
        splitter = module.TextSplitter(scenario.max_chunk_size)

    chunks = splitter.chunks(text)
    return len(chunks)


def _run_semchunk(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("semchunk")
    if module is None:
        raise ImportError("semchunk is unavailable")

    chunkerify = getattr(module, "chunkerify", None)
    if callable(chunkerify):
        token_counter = lambda s: len(s.split())
        token_budget = max(32, scenario.max_chunk_size // 4)
        chunker = chunkerify(token_counter, chunk_size=token_budget)
        return len(list(chunker(text)))

    for candidate in ("split", "chunk_text", "chunk"):
        fn = getattr(module, candidate, None)
        if not callable(fn):
            continue

        for kwargs in (
            {"chunk_size": scenario.max_chunk_size},
            {"max_chunk_size": scenario.max_chunk_size},
            {},
        ):
            try:
                output = fn(text, **kwargs)
                return len(list(output))
            except TypeError:
                continue

    raise RuntimeError("semchunk integration is unavailable for this version")


def _run_astchunk(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("astchunk")
    if module is None:
        module = _optional_import("astchunker")
    if module is None:
        raise ImportError("astchunk/astchunker module is unavailable")

    for candidate in ("chunk_text", "chunk"):
        fn = getattr(module, candidate, None)
        if not callable(fn):
            continue

        for kwargs in (
            {"max_chunk_size": scenario.max_chunk_size},
            {"chunk_size": scenario.max_chunk_size},
            {},
        ):
            try:
                output = fn(text, **kwargs)
                return len(list(output))
            except TypeError:
                continue

    chunker_cls = getattr(module, "ASTChunker", None) or getattr(module, "Chunker", None)
    if chunker_cls is not None:
        for kwargs in (
            {"max_chunk_size": scenario.max_chunk_size},
            {"chunk_size": scenario.max_chunk_size},
            {},
        ):
            try:
                chunker = chunker_cls(**kwargs)
                run_fn = getattr(chunker, "chunk", None)
                if callable(run_fn):
                    output = run_fn(text)
                    return len(list(output))
            except TypeError:
                continue

    raise RuntimeError("astchunk integration is unavailable for this version")


def _benchmark_runner(
    tool_name: str,
    runner: Callable[[str, Scenario, Path], int],
    scenario: Scenario,
) -> ToolResult:
    text = scenario.path.read_text(encoding="utf-8")
    data_bytes = len(text.encode("utf-8"))

    started = perf_counter()
    try:
        chunk_count = int(runner(text, scenario, scenario.path))
        elapsed = perf_counter() - started
        mbps = (data_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
        return ToolResult(
            tool=tool_name,
            scenario=scenario.name,
            data_bytes=data_bytes,
            chunks=chunk_count,
            seconds=elapsed,
            mbps=mbps,
            status="ok",
            detail="",
        )
    except ImportError as exc:
        return ToolResult(
            tool=tool_name,
            scenario=scenario.name,
            data_bytes=data_bytes,
            chunks=-1,
            seconds=0.0,
            mbps=0.0,
            status="unavailable",
            detail=str(exc),
        )
    except Exception as exc:
        return ToolResult(
            tool=tool_name,
            scenario=scenario.name,
            data_bytes=data_bytes,
            chunks=-1,
            seconds=0.0,
            mbps=0.0,
            status="error",
            detail=f"{type(exc).__name__}: {exc}",
        )


def run() -> int:
    include_extra = "--include-extra" in sys.argv

    runners: list[tuple[str, Callable[[str, Scenario, Path], int]]] = [
        ("omnichunk", _run_omnichunk),
        ("langchain_recursive", _run_langchain_recursive),
        ("semantic_text_splitter", _run_semantic_text_splitter),
    ]
    if include_extra:
        runners.extend(
            [
                ("semchunk", _run_semchunk),
                ("astchunk", _run_astchunk),
            ]
        )

    print("Tool,Scenario,Bytes,Chunks,Seconds,MBps,Status,Detail")

    summary: dict[str, list[ToolResult]] = {}
    for tool_name, runner in runners:
        for scenario in SCENARIOS:
            result = _benchmark_runner(tool_name, runner, scenario)
            summary.setdefault(tool_name, []).append(result)
            print(
                f"{result.tool},{result.scenario},{result.data_bytes},{result.chunks},"
                f"{result.seconds:.6f},{result.mbps:.3f},{result.status},"
                f"{result.detail.replace(',', ';')}"
            )

    print("Tool,TOTAL,-,-,-,-,Status")
    for tool_name, rows in summary.items():
        statuses = {r.status for r in rows}
        total_bytes = sum(r.data_bytes for r in rows if r.status == "ok")
        total_seconds = sum(r.seconds for r in rows if r.status == "ok")
        total_mbps = (total_bytes / (1024 * 1024)) / total_seconds if total_seconds > 0 else 0.0

        if statuses == {"ok"}:
            print(f"{tool_name},TOTAL,{total_bytes},-,{total_seconds:.6f},{total_mbps:.3f},ok")
        elif "ok" in statuses:
            print(f"{tool_name},TOTAL,{total_bytes},-,{total_seconds:.6f},{total_mbps:.3f},partial")
        elif "unavailable" in statuses and len(statuses) == 1:
            print(f"{tool_name},TOTAL,0,-,0.000000,0.000,unavailable")
        else:
            print(f"{tool_name},TOTAL,0,-,0.000000,0.000,error")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
