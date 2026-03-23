from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omnichunk import __version__
from omnichunk.chunker import Chunker
from omnichunk.eval import eval_report_to_dict, evaluate_chunks
from omnichunk.serialization import chunk_from_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omnichunk",
        description="Structure-aware deterministic chunking for files and directories.",
    )
    parser.add_argument("target", help="File or directory to chunk")
    parser.add_argument("--glob", default="**/*", help="Glob pattern for directory mode")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude pattern for directory mode (repeatable)",
    )
    parser.add_argument("--max-size", type=int, default=1500, help="Maximum chunk size")
    parser.add_argument("--min-size", type=int, default=50, help="Minimum chunk size")
    parser.add_argument(
        "--size-unit",
        choices=["tokens", "chars", "nws"],
        default="tokens",
        help="Chunk size measurement unit",
    )
    parser.add_argument(
        "--nws-backend",
        choices=["auto", "python", "rust"],
        default="auto",
        help="Backend used for non-whitespace cumulative sizing",
    )
    parser.add_argument(
        "--context-mode",
        choices=["none", "minimal", "full"],
        default="full",
        help="Context detail mode",
    )
    parser.add_argument(
        "--format",
        choices=["json", "jsonl", "csv"],
        default="json",
        help="Output format for chunk payload",
    )
    parser.add_argument("--output", default=None, help="Optional output file path")
    parser.add_argument("--stats", action="store_true", help="Print chunk stats JSON")
    parser.add_argument("--concurrency", type=int, default=10, help="Directory worker count")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden files")
    parser.add_argument("--encoding", default="utf-8", help="File decoding encoding")
    parser.add_argument(
        "--overlap",
        type=_parse_overlap,
        default=None,
        help="Token overlap count or ratio (e.g. 64 or 0.2)",
    )
    parser.add_argument(
        "--overlap-lines",
        type=int,
        default=0,
        help="Number of trailing lines to include in contextualized overlap",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"omnichunk {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(argv if argv is not None else sys.argv[1:])
    if argv_list and argv_list[0] == "eval":
        return eval_main(argv_list[1:])
    if argv_list and argv_list[0] == "serve":
        return serve_main(argv_list[1:])
    return chunk_main(argv_list)


def serve_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="omnichunk serve",
        description="Run JSON-RPC HTTP server (MCP-style tools; stdlib only).",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Required flag: start the MCP-style JSON-RPC server",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=3333, help="TCP port")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON file merged into default Chunker options for each request",
    )
    args = parser.parse_args(list(argv))
    if not args.mcp:
        print("serve requires --mcp (JSON-RPC tools over HTTP)", file=sys.stderr)
        return 2
    from omnichunk.mcp.server import run_mcp_server

    tools = "chunk_file, chunk_directory, build_graph, semantic_chunk"
    print(
        f"omnichunk MCP JSON-RPC — POST http://{args.host}:{args.port}/ ({tools})",
        flush=True,
    )
    run_mcp_server(args.host, args.port, config_path=args.config)
    return 0


def eval_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="omnichunk eval",
        description=(
            "Evaluate chunk quality metrics from JSONL "
            "(from chunk_to_dict / omnichunk export)."
        ),
    )
    parser.add_argument(
        "chunks_jsonl",
        type=Path,
        help="Path to JSONL file with one chunk dict per line",
    )
    parser.add_argument(
        "--metrics",
        default="all",
        help=(
            "Comma-separated metric names or 'all' "
            "(reconstruction,density,coherence,boundary_quality,coverage)"
        ),
    )
    parser.add_argument(
        "--source",
        default=None,
        type=Path,
        help="Original source text file for reconstruction and coverage metrics",
    )
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    args = parser.parse_args(list(argv))

    path = args.chunks_jsonl
    if not path.exists():
        print(f"File does not exist: {path}", file=sys.stderr)
        return 2

    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(chunk_from_dict(json.loads(line)))

    source_text = None
    if args.source is not None:
        source_text = args.source.read_text(encoding="utf-8")

    m = args.metrics.strip()
    if m == "all":
        metrics_any: Any = "all"
    else:
        metrics_any = [x.strip() for x in m.split(",") if x.strip()]

    report = evaluate_chunks(chunks, source=source_text, metrics=metrics_any)
    payload = json.dumps(eval_report_to_dict(report), ensure_ascii=False, indent=2) + "\n"
    _write_text(payload, args.output)
    return 0


def chunk_main(argv: Sequence[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv))

    target = Path(args.target)
    if not target.exists():
        print(f"Target does not exist: {target}", file=sys.stderr)
        return 2

    chunker = Chunker(
        max_chunk_size=args.max_size,
        min_chunk_size=args.min_size,
        size_unit=args.size_unit,
        nws_backend=args.nws_backend,
        context_mode=args.context_mode,
        overlap=args.overlap,
        overlap_lines=max(0, int(args.overlap_lines)),
    )

    errors: list[dict[str, str]] = []
    chunks = []

    if target.is_dir():
        results = chunker.chunk_directory(
            str(target),
            glob=args.glob,
            exclude=args.exclude,
            concurrency=max(1, int(args.concurrency)),
            encoding=args.encoding,
            include_hidden=bool(args.include_hidden),
        )
        for result in results:
            chunks.extend(result.chunks)
            if result.error:
                errors.append({"filepath": result.filepath, "error": result.error})
    else:
        try:
            chunks = chunker.chunk_file(str(target), encoding=args.encoding)
        except Exception as exc:
            errors.append({"filepath": str(target), "error": str(exc)})

    if args.stats:
        payload = _build_stats_payload(
            chunker=chunker,
            chunks=chunks,
            errors=errors,
            min_chunk_size=args.min_size,
            max_chunk_size=args.max_size,
            size_unit=args.size_unit,
        )
        _write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", args.output)
    else:
        _write_chunks_payload(
            chunker=chunker,
            chunks=chunks,
            output_format=args.format,
            output_path=args.output,
        )

    for error in errors:
        print(f"[{error['filepath']}] {error['error']}", file=sys.stderr)

    return 1 if errors else 0


def _build_stats_payload(
    *,
    chunker: Chunker,
    chunks: list[Any],
    errors: list[dict[str, str]],
    min_chunk_size: int,
    max_chunk_size: int,
    size_unit: str,
) -> dict[str, Any]:
    stats = chunker.chunk_stats(chunks, size_unit=size_unit)
    quality = chunker.quality_scores(
        chunks,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        size_unit=size_unit,
    )

    average_quality = 0.0
    if quality:
        average_quality = sum(item.overall for item in quality) / len(quality)

    return {
        "total_chunks": stats.total_chunks,
        "average_size": stats.average_size,
        "min_size": stats.min_size,
        "max_size": stats.max_size,
        "size_unit": stats.size_unit,
        "entity_distribution": stats.entity_distribution,
        "average_quality": round(average_quality, 4),
        "failed_files": len(errors),
    }


def _write_chunks_payload(
    *,
    chunker: Chunker,
    chunks: list[Any],
    output_format: str,
    output_path: str | None,
) -> None:
    if output_format == "jsonl":
        payload = chunker.to_jsonl(chunks, output_path=output_path)
        if output_path is None:
            sys.stdout.write(payload)
        return

    if output_format == "csv":
        payload = chunker.to_csv(chunks, output_path=output_path)
        if output_path is None:
            sys.stdout.write(payload)
        return

    payload = json.dumps(chunker.to_dicts(chunks), ensure_ascii=False, indent=2) + "\n"
    _write_text(payload, output_path)


def _write_text(payload: str, output_path: str | None) -> None:
    if output_path is None:
        sys.stdout.write(payload)
        return

    Path(output_path).write_text(payload, encoding="utf-8")


def _parse_overlap(value: str) -> int | float:
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("Overlap value cannot be empty")

    if "." in text:
        try:
            parsed = float(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Overlap must be int or float") from exc
        if parsed < 0:
            raise argparse.ArgumentTypeError("Overlap cannot be negative")
        return parsed

    try:
        parsed_int = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Overlap must be int or float") from exc

    if parsed_int < 0:
        raise argparse.ArgumentTypeError("Overlap cannot be negative")
    return parsed_int


if __name__ == "__main__":
    raise SystemExit(main())
