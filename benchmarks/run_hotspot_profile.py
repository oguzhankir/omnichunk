# ruff: noqa: E402
from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workloads import collect_corpus_entries

from omnichunk import Chunker
from omnichunk.sizing import get_nws_backend_status

_HOT_PATTERNS: tuple[str, ...] = (
    "omnichunk/sizing/nws.py",
    "omnichunk/windowing/split.py",
    "omnichunk/windowing/greedy.py",
    "omnichunk/context/entities.py",
    "omnichunk/context/siblings.py",
    "omnichunk/util/text_index.py",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run cProfile on large corpus chunking and print hotspot candidates.",
    )
    parser.add_argument(
        "--mode",
        choices=["fixtures", "mega-python", "directory"],
        default="mega-python",
        help="Corpus generation mode",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=80,
        help="Repeat count for fixture/mega modes",
    )
    parser.add_argument("--directory", default=None, help="Directory path for directory mode")
    parser.add_argument("--glob", default="**/*", help="Glob used in directory mode")
    parser.add_argument("--max-files", type=int, default=500, help="Max files in directory mode")
    parser.add_argument("--encoding", default="utf-8", help="File decoding encoding")
    parser.add_argument("--max-size", type=int, default=420, help="Maximum chunk size")
    parser.add_argument("--min-size", type=int, default=80, help="Minimum chunk size")
    parser.add_argument(
        "--size-unit",
        choices=["tokens", "chars", "nws"],
        default="chars",
        help="Chunk sizing unit",
    )
    parser.add_argument(
        "--nws-backend",
        choices=["auto", "python", "rust"],
        default="auto",
        help="NWS preprocessing backend",
    )
    parser.add_argument(
        "--sort",
        choices=["cumulative", "tottime", "time", "calls"],
        default="cumulative",
        help="cProfile sort key",
    )
    parser.add_argument("--limit", type=int, default=40, help="Top function rows to print")
    parser.add_argument(
        "--profile-output",
        default=None,
        help="Optional path to dump raw cProfile stats",
    )
    parser.add_argument(
        "--py-spy-hint",
        action="store_true",
        help="Print a py-spy command hint for flamegraph profiling",
    )
    return parser


def run() -> int:
    args = _build_parser().parse_args()

    entries = collect_corpus_entries(
        mode=args.mode,
        repeat=max(1, int(args.repeat)),
        directory=args.directory,
        glob_pattern=args.glob,
        max_files=max(1, int(args.max_files)),
        encoding=args.encoding,
    )
    if not entries:
        print("No corpus entries found.", file=sys.stderr)
        return 1

    chunker = Chunker(
        max_chunk_size=int(args.max_size),
        min_chunk_size=int(args.min_size),
        size_unit=str(args.size_unit),
        nws_backend=str(args.nws_backend),
    )

    profiler = cProfile.Profile()
    total_bytes = 0
    total_chunks = 0

    profiler.enable()
    started = perf_counter()
    for entry in entries:
        total_bytes += len(entry.text.encode("utf-8"))
        chunks = chunker.chunk(entry.filepath, entry.text)
        total_chunks += len(chunks)
    elapsed = perf_counter() - started
    profiler.disable()

    throughput = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
    backend_status = get_nws_backend_status(str(args.nws_backend))

    print("ProfileSummary")
    print(f"- mode: {args.mode}")
    print(f"- files: {len(entries)}")
    print(f"- bytes: {total_bytes}")
    print(f"- chunks: {total_chunks}")
    print(f"- seconds: {elapsed:.6f}")
    print(f"- mbps: {throughput:.3f}")
    print(
        f"- nws_backend: {backend_status['selected']} (active={backend_status['active']}, "
        f"available={backend_status['available']})"
    )
    if backend_status["reason"]:
        print(f"- backend_reason: {backend_status['reason']}")

    if args.profile_output:
        out_path = Path(args.profile_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(out_path))
        print(f"- profile_output: {out_path}")

    print("\nTopFunctions")
    stats = pstats.Stats(profiler).sort_stats(str(args.sort))
    stats.print_stats(max(1, int(args.limit)))

    print("\nHotspotCandidates")
    for pattern in _HOT_PATTERNS:
        print(f"\n# {pattern}")
        stats.print_stats(pattern)

    if args.py_spy_hint:
        cmd = (
            "py-spy record -o profile.svg -- python benchmarks/run_large_corpus.py "
            f"--mode {args.mode} --repeat {int(args.repeat)} --max-size {int(args.max_size)} "
            f"--min-size {int(args.min_size)} --size-unit {args.size_unit} "
            f"--nws-backend {args.nws_backend}"
        )
        if args.mode == "directory" and args.directory:
            cmd += (
                f" --directory {args.directory} --glob '{args.glob}' "
                f"--max-files {int(args.max_files)}"
            )
        print("\nPySpyHint")
        print(cmd)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
