# ruff: noqa: E402
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import re
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

# Data rows from pstats.print_stats() — ncalls may be "prim/total" for recursive calls.
# Times are usually 0.000; tiny entries may appear as 1e-05.
_FLOAT = r"(?:\d+\.\d+|\d+(?:\.\d+)?[eE][+-]?\d+)"
_STAT_LINE_RE = re.compile(
    rf"^\s*(?P<ncalls>\d+(?:/\d+)?)\s+"
    rf"(?P<tottime>{_FLOAT})\s+{_FLOAT}\s+"
    rf"(?P<cumtime>{_FLOAT})\s+{_FLOAT}\s+"
    rf"(?P<loc>.+)$"
)


def _parse_ncalls(raw: str) -> int:
    if "/" in raw:
        return int(raw.split("/")[-1])
    return int(raw)


def _parse_location(loc: str) -> tuple[str, int, str] | None:
    """Parse 'path:lineno(name)' from pstats last column."""
    if "(" not in loc or ")" not in loc:
        return None
    head, paren = loc.rsplit("(", 1)
    func = paren.rstrip(")")
    if ":" not in head:
        return None
    path, line_s = head.rsplit(":", 1)
    try:
        lineno = int(line_s)
    except ValueError:
        return None
    return path.replace("\\", "/"), lineno, func


def _parse_print_stats_table(raw: str) -> list[dict[str, object]]:
    """Parse cProfile pstats.print_stats() text into structured rows."""
    rows: list[dict[str, object]] = []
    seen_header = False
    for line in raw.splitlines():
        if "ncalls" in line and "tottime" in line and "cumtime" in line and "filename" in line:
            seen_header = True
            continue
        if not seen_header:
            continue
        m = _STAT_LINE_RE.match(line)
        if not m:
            continue
        loc = m.group("loc")
        parsed = _parse_location(loc)
        if parsed is None:
            continue
        filename, _lineno, function = parsed
        rows.append(
            {
                "filename": filename,
                "function": function,
                "tottime": float(m.group("tottime")),
                "cumtime": float(m.group("cumtime")),
                "calls": _parse_ncalls(m.group("ncalls")),
                "raw_location": loc,
            }
        )
    return rows


def _normalize_filter_path(filename: str) -> str:
    """Strip to package-relative path (avoid matching repo folder .../omnichunk/)."""
    fn = filename.replace("\\", "/")
    if "/src/omnichunk/" in fn:
        i = fn.index("/src/omnichunk/") + len("/src/")
        return fn[i:]
    if "/site-packages/omnichunk/" in fn:
        i = fn.index("/site-packages/omnichunk/") + len("/site-packages/")
        return fn[i:]
    return fn


def _row_matches_filters(norm_path: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    return any(p in norm_path for p in patterns)


def _sort_key(row: dict[str, object]) -> tuple[float, float, str]:
    return (
        -float(row["tottime"]),
        -float(row["cumtime"]),
        str(row["function"]),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deep cProfile run: structured hotspot table (tottime) for one corpus pass.",
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
        default=60,
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
    parser.add_argument("--limit", type=int, default=25, help="Top rows to emit after filtering")
    parser.add_argument(
        "--filter-patterns",
        nargs="*",
        default=(),
        help=(
            "Substring filters on normalized paths (omnichunk/...); "
            "if none match, show global top-N"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Text table output path (also printed to stdout)",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Structured JSON output path",
    )
    return parser


def _format_table(rows: list[dict[str, object]]) -> str:
    lines = [
        f"{'Rank':>4}  {'tottime':>8}  {'cumtime':>8}  {'calls':>8}     function",
        "─" * 74,
    ]
    for i, row in enumerate(rows, start=1):
        norm = _normalize_filter_path(str(row["filename"]))
        func_disp = f"{norm}:{row['function']}"
        lines.append(
            f"{i:>4}  {float(row['tottime']):>7.3f}s  {float(row['cumtime']):>7.3f}s  "
            f"{int(row['calls']):>8}     {func_disp}"
        )
    return "\n".join(lines) + "\n"


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

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

    patterns = tuple(str(p).replace("\\", "/") for p in (args.filter_patterns or ()))

    pr = cProfile.Profile()
    pr.enable()
    started = perf_counter()
    for entry in entries:
        _ = chunker.chunk(entry.filepath, entry.text)
    total_seconds = perf_counter() - started
    pr.disable()

    stream = io.StringIO()
    stats = pstats.Stats(pr, stream=stream)
    stats.sort_stats("tottime")
    stats.print_stats()
    raw = stream.getvalue()

    rows = _parse_print_stats_table(raw)
    if not rows:
        # Fallback: build from Stats.stats if text parsing failed (e.g. locale/format).
        st2 = pstats.Stats(pr)
        st2.sort_stats("tottime")
        for (fn, _ln, funcname), (_cc, nc, tt, ct, _callers) in st2.stats.items():
            if not isinstance(fn, str):
                continue
            rows.append(
                {
                    "filename": fn.replace("\\", "/"),
                    "function": funcname,
                    "tottime": float(tt),
                    "cumtime": float(ct),
                    "calls": int(nc),
                    "raw_location": f"{fn}:{funcname}",
                }
            )

    for row in rows:
        row["norm_path"] = _normalize_filter_path(str(row["filename"]))

    filtered = [r for r in rows if _row_matches_filters(str(r["norm_path"]), patterns)]
    pool = filtered if filtered else rows
    pool_sorted = sorted(pool, key=_sort_key)
    limit = max(1, int(args.limit))
    top = pool_sorted[:limit]

    backend_status = get_nws_backend_status(str(args.nws_backend))
    denom = total_seconds if total_seconds > 0 else 1.0

    json_hotspots: list[dict[str, object]] = []
    for i, row in enumerate(top, start=1):
        tt = float(row["tottime"])
        json_hotspots.append(
            {
                "rank": i,
                "filename": str(row["norm_path"]),
                "function": str(row["function"]),
                "tottime": round(tt, 6),
                "cumtime": round(float(row["cumtime"]), 6),
                "calls": int(row["calls"]),
                "tottime_pct": round(100.0 * tt / denom, 4),
            }
        )

    payload = {
        "mode": str(args.mode),
        "repeat": int(args.repeat),
        "total_seconds": round(total_seconds, 6),
        "nws_backend": str(backend_status["selected"]),
        "nws_backend_active": bool(backend_status["active"]),
        "filter_patterns": list(patterns),
        "filter_matched_any": bool(filtered),
        "top_hotspots": json_hotspots,
    }

    table = _format_table(top)
    print(table, end="")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(table, encoding="utf-8")

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
