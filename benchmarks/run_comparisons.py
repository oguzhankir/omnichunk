# ruff: noqa: E402
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BENCH_DIR = Path(__file__).resolve().parent
for _p in (SRC, BENCH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from comparison_format import (
    aggregate_tool_totals,
    build_comparison_json_payload,
    format_speedup_lines,
)
from run_benchmarks import SCENARIOS, Scenario
from workloads import collect_corpus_entries

from omnichunk import Chunker


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


def _size_counter(scenario: Scenario) -> Callable[[str], int]:
    if scenario.size_unit == "chars":
        return len
    if scenario.size_unit == "tokens":
        import tiktoken

        tokenizer = tiktoken.get_encoding("cl100k_base")
        return lambda text: len(tokenizer.encode(text))
    raise ImportError(f"Unsupported comparison budget unit: {scenario.size_unit}")


def _validated_count(
    chunks: Iterable[str], scenario: Scenario, counter: Callable[[str], int]
) -> int:
    count = 0
    for text in chunks:
        size = counter(text)
        if size > scenario.max_chunk_size:
            raise ValueError(
                f"Output exceeds shared {scenario.size_unit} budget: "
                f"{size} > {scenario.max_chunk_size}"
            )
        count += 1
    return count


def _run_omnichunk(text: str, scenario: Scenario, filepath: Path) -> int:
    counter = _size_counter(scenario)
    chunker = Chunker()
    chunks = chunker.chunk(
        str(filepath),
        text,
        max_chunk_size=scenario.max_chunk_size,
        min_chunk_size=scenario.min_chunk_size,
        size_unit=scenario.size_unit,
        tokenizer="cl100k_base" if scenario.size_unit == "tokens" else None,
        context_mode="none",
        overlap=0,
    )
    return _validated_count((chunk.contextualized_text for chunk in chunks), scenario, counter)


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

    counter = _size_counter(scenario)
    splitter = splitter_cls(
        chunk_size=scenario.max_chunk_size,
        chunk_overlap=0,
        length_function=counter,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_text(text)
    return _validated_count(chunks, scenario, counter)


def _run_semantic_text_splitter(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("semantic_text_splitter")
    if module is None:
        raise ImportError("semantic_text_splitter is unavailable")

    counter = _size_counter(scenario)
    splitter_cls = (
        module.MarkdownSplitter
        if filepath.suffix.lower() in {".md", ".markdown"}
        else module.TextSplitter
    )
    if scenario.size_unit == "chars":
        splitter = splitter_cls(scenario.max_chunk_size, overlap=0)
    else:
        factory = getattr(splitter_cls, "from_callback", None)
        if not callable(factory):
            raise ImportError("semantic_text_splitter lacks an explicit tokenizer callback API")
        splitter = factory(counter, scenario.max_chunk_size, overlap=0)
    chunks = splitter.chunks(text)
    return _validated_count(chunks, scenario, counter)


def _run_semchunk(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("semchunk")
    if module is None:
        raise ImportError("semchunk is unavailable")

    chunkerify = getattr(module, "chunkerify", None)
    if not callable(chunkerify):
        raise ImportError("semchunk lacks an explicit counter/budget API")
    counter = _size_counter(scenario)
    chunker = chunkerify(counter, chunk_size=scenario.max_chunk_size)
    return _validated_count(chunker(text, overlap=0), scenario, counter)


def _run_astchunk(text: str, scenario: Scenario, filepath: Path) -> int:
    module = _optional_import("astchunk")
    if module is None:
        module = _optional_import("astchunker")
    if module is None:
        raise ImportError("astchunk/astchunker module is unavailable")

    raise ImportError(
        "astchunk excluded: shared budget unit, tokenizer and zero-overlap semantics "
        "are not verified for this adapter"
    )


def _benchmark_runner(
    tool_name: str,
    runner: Callable[[str, Scenario, Path], int],
    scenario: Scenario,
) -> ToolResult:
    text = scenario.path.read_text(encoding="utf-8")
    data_bytes = len(text.encode("utf-8"))

    # Warmup (not timed): avoids attributing lazy imports / tokenizer init to the first scenario
    # only (e.g. LangChain first call ~seconds, second ~microseconds on the same process).
    with contextlib.suppress(Exception):
        int(runner(text, scenario, scenario.path))

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


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare omnichunk vs optional third-party splitters.")
    p.add_argument(
        "--corpus",
        choices=("all", "smoke", "mega-fixture", "mega-python"),
        default="all",
        help=(
            "all: every SCENARIOS entry (small fixtures + mega_python_50x). "
            "smoke: small fixtures only. mega-fixture: only mega_python_50x on disk. "
            "mega-python: synthetic corpus (workloads), --repeat, written to a temp file."
        ),
    )
    p.add_argument(
        "--repeat",
        type=int,
        default=50,
        help="mega-python corpus only: repeat count for python_complex blocks (default 50)",
    )
    p.add_argument(
        "--include-extra",
        action="store_true",
        help="Also run astchunk/astchunker (semchunk is included by default)",
    )
    p.add_argument(
        "--save",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write structured JSON comparison results to PATH",
    )
    p.add_argument(
        "--no-table",
        action="store_true",
        help="Suppress descriptive summary and same-scenario timing ratios (CSV only)",
    )
    return p.parse_args(argv)


def _comparison_scenarios(args: argparse.Namespace) -> tuple[list[Scenario], Path | None]:
    """
    Returns (scenarios, temp_dir_to_remove). temp_dir is set only for mega-python corpus.
    """
    temp_dir: Path | None = None
    if args.corpus == "all":
        return list(SCENARIOS), None
    if args.corpus == "smoke":
        return [s for s in SCENARIOS if s.name != "mega_python_50x"], None
    if args.corpus == "mega-fixture":
        found = [s for s in SCENARIOS if s.name == "mega_python_50x"]
        if not found:
            print(
                "mega-fixture: mega_python_50x not in SCENARIOS "
                "(missing tests/fixtures/mega_python_50x.py?)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return found, None
    if args.corpus == "mega-python":
        repeat = max(1, int(args.repeat))
        entries = collect_corpus_entries(
            mode="mega-python",
            repeat=repeat,
            directory=None,
            glob_pattern="**/*",
            max_files=500,
        )
        if not entries:
            print("mega-python: collect_corpus_entries returned no entries", file=sys.stderr)
            raise SystemExit(2)
        tmp = Path(tempfile.mkdtemp(prefix="omnichunk_cmp_"))
        temp_dir = tmp
        path = tmp / "mega_python.py"
        path.write_text(entries[0].text, encoding="utf-8")
        return [
            Scenario(
                f"mega_python_r{repeat}",
                path,
                max_chunk_size=512,
                min_chunk_size=128,
                size_unit="chars",
            )
        ], temp_dir


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    scenarios, temp_cmp_dir = _comparison_scenarios(args)

    runners: list[tuple[str, Callable[[str, Scenario, Path], int]]] = [
        ("omnichunk", _run_omnichunk),
        ("langchain_recursive", _run_langchain_recursive),
        ("semantic_text_splitter", _run_semantic_text_splitter),
        ("semchunk", _run_semchunk),
    ]
    if args.include_extra:
        runners.append(("astchunk", _run_astchunk))

    tool_order = [t[0] for t in runners]

    print("Tool,Scenario,Bytes,Chunks,Seconds,MBps,Status,Detail")

    summary: dict[str, list[ToolResult]] = {}
    try:
        for tool_name, runner in runners:
            for scenario in scenarios:
                result = _benchmark_runner(tool_name, runner, scenario)
                summary.setdefault(tool_name, []).append(result)
                print(
                    f"{result.tool},{result.scenario},{result.data_bytes},{result.chunks},"
                    f"{result.seconds:.6f},{result.mbps:.3f},{result.status},"
                    f"{result.detail.replace(',', ';')}"
                )
    finally:
        if temp_cmp_dir is not None:
            shutil.rmtree(temp_cmp_dir, ignore_errors=True)

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

    aggregates = aggregate_tool_totals(tool_rows=summary)
    eligible = {
        name: aggregate
        for name, aggregate in aggregates.items()
        if aggregate.get("status") == "ok" and len(summary[name]) == len(scenarios)
    }
    # Partial runs cover different input and cannot supply a comparison denominator.
    omni_sec = float(eligible.get("omnichunk", {}).get("total_seconds", 0.0))

    if not args.no_table:
        print()
        print(
            "Descriptive timings for this workload; no library ranking or retrieval-quality claim."
        )
        for line in format_speedup_lines(
            omnichunk_seconds=omni_sec,
            aggregates=eligible,
            tool_order=tool_order,
        ):
            print(line)

    if args.save is not None:
        payload = build_comparison_json_payload(
            scenario_names=[s.name for s in scenarios],
            tool_order=tool_order,
            aggregates=aggregates,
            winner=None,
        )
        payload["speedup"] = {
            f"omnichunk_vs_{name}": round(float(row["total_seconds"]) / omni_sec, 4)
            for name, row in eligible.items()
            if name != "omnichunk" and omni_sec > 0 and float(row["total_seconds"]) > 0
        }
        payload["configuration"] = {
            "context_mode": "none",
            "overlap": 0,
            "tokenizer_for_token_scenarios": "cl100k_base",
            "scenarios": [
                {
                    "name": item.name,
                    "size_unit": item.size_unit,
                    "max_chunk_size": item.max_chunk_size,
                }
                for item in scenarios
            ],
        }
        payload["results"] = [asdict(row) for rows in summary.values() for row in rows]
        payload["interpretation"] = "Descriptive same-workload timing only; no library ranking."
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return int(any(row.status == "error" for rows in summary.values() for row in rows))


def _flush_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()


if __name__ == "__main__":
    # semchunk pulls in `multiprocess`, whose ResourceTracker __del__ can raise on Python 3.12
    # during normal interpreter shutdown ("Exception ignored in ..."). os._exit skips that path.
    bench_exit = run()
    _flush_streams()
    os._exit(int(bench_exit))
