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
from collections.abc import Callable
from dataclasses import dataclass
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
    comparison_exit_code,
    format_comparison_summary_table,
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

        def token_counter(s: str) -> int:
            return len(s.split())

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
        help="Suppress ASCII summary table and speedup lines (CSV only)",
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
    timed: list[tuple[str, float]] = []
    for name in tool_order:
        agg = aggregates.get(name, {})
        if agg.get("status") in ("ok", "partial") and float(agg.get("total_seconds", 0.0)) > 0:
            timed.append((name, float(agg["total_seconds"])))
    winner: str | None = min(timed, key=lambda x: (x[1], x[0]))[0] if timed else None

    if not args.no_table:
        print()
        print(format_comparison_summary_table(tool_order=tool_order, aggregates=aggregates))
        omni_sec = float(aggregates.get("omnichunk", {}).get("total_seconds", 0.0))
        for line in format_speedup_lines(
            omnichunk_seconds=omni_sec,
            aggregates=aggregates,
            tool_order=tool_order,
        ):
            print(line)

    if args.save is not None:
        payload = build_comparison_json_payload(
            scenario_names=[s.name for s in scenarios],
            tool_order=tool_order,
            aggregates=aggregates,
            winner=winner,
        )
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return comparison_exit_code(aggregates=aggregates, tool_order=tool_order)


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
