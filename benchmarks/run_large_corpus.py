# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workloads import collect_corpus_entries

from omnichunk import Chunker
from omnichunk.sizing import get_nws_backend_status


@dataclass(frozen=True)
class FileTiming:
    filepath: str
    bytes: int
    chunks: int
    seconds: float


@dataclass(frozen=True)
class CorpusRunResult:
    mode: str
    files: int
    bytes: int
    chunks: int
    seconds: float
    mbps: float
    nws_backend: str
    backend_available: bool
    backend_active: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chunk large corpora to detect throughput and slow files.",
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
        help="Repeat count for fixture and mega-python modes",
    )
    parser.add_argument(
        "--directory",
        default=None,
        help="Directory path used only in directory mode",
    )
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
        "--top-slowest",
        type=int,
        default=10,
        help="Print this many slowest files by chunk duration",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path for JSON summary output",
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

    timings: list[FileTiming] = []
    total_bytes = 0
    total_chunks = 0

    started = perf_counter()
    for entry in entries:
        data_bytes = len(entry.text.encode("utf-8"))
        run_started = perf_counter()
        chunks = chunker.chunk(entry.filepath, entry.text)
        elapsed = perf_counter() - run_started

        total_bytes += data_bytes
        total_chunks += len(chunks)
        timings.append(
            FileTiming(
                filepath=entry.filepath,
                bytes=data_bytes,
                chunks=len(chunks),
                seconds=elapsed,
            )
        )
    total_seconds = perf_counter() - started

    mbps = (total_bytes / (1024 * 1024)) / total_seconds if total_seconds > 0 else 0.0
    backend_status = get_nws_backend_status(str(args.nws_backend))

    summary = CorpusRunResult(
        mode=str(args.mode),
        files=len(entries),
        bytes=total_bytes,
        chunks=total_chunks,
        seconds=total_seconds,
        mbps=mbps,
        nws_backend=str(backend_status["selected"]),
        backend_available=bool(backend_status["available"]),
        backend_active=bool(backend_status["active"]),
    )

    print("Mode,Files,Bytes,Chunks,Seconds,MBps,NWSBackend,BackendAvailable,BackendActive")
    print(
        f"{summary.mode},{summary.files},{summary.bytes},{summary.chunks},{summary.seconds:.6f},"
        f"{summary.mbps:.3f},{summary.nws_backend},{str(summary.backend_available).lower()},"
        f"{str(summary.backend_active).lower()}"
    )

    slowest = sorted(timings, key=lambda item: item.seconds, reverse=True)[
        : max(1, args.top_slowest)
    ]
    print("SlowFile,Bytes,Chunks,Seconds")
    for item in slowest:
        print(f"{item.filepath},{item.bytes},{item.chunks},{item.seconds:.6f}")

    if args.json_output:
        payload = {
            "summary": asdict(summary),
            "slowest": [asdict(item) for item in slowest],
        }
        Path(args.json_output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
