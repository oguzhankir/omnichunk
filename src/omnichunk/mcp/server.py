"""
JSON-RPC 2.0 over HTTP POST — exposes chunking tools without extra dependencies.

For full MCP SDK / stdio transport, install ``omnichunk[mcp]`` (reserved extra).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from omnichunk import Chunker, build_chunk_graph
from omnichunk.chunker import _coerce_option_dict
from omnichunk.serialization import chunk_from_dict, chunk_to_dict

# RPC-only keys (not Chunker constructor / ChunkOptions).
_RESERVED_PARAMS = frozenset(
    {
        "path",
        "glob",
        "exclude",
        "encoding",
        "include_hidden",
        "concurrency",
        "chunks",
        "filepath",
        "content",
        "embed_backend",
        "min_entity_occurrences",
        "window",
        "threshold",
    }
)


def _mock_embed_fn() -> Callable[[list[str]], Any]:
    """Tiny deterministic embeddings for ``semantic_chunk`` with ``embed_backend=mock``."""

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            n = len(t.encode("utf-8"))
            out.append([float(n % 97), float((n // 97) % 97), 0.0])
        return out

    return embed


def _chunker_from_params(params: dict[str, Any]) -> Chunker:
    raw = {k: v for k, v in params.items() if k not in _RESERVED_PARAMS}
    return Chunker(**_coerce_option_dict(raw))


def _handle_tool(method: str, params: dict[str, Any]) -> Any:
    if method == "chunk_file":
        path = params.get("path")
        if not path:
            raise ValueError("chunk_file requires path")
        encoding = str(params.get("encoding", "utf-8"))
        ck = _chunker_from_params(params)
        chunks = ck.chunk_file(str(path), encoding=encoding)
        return [chunk_to_dict(c) for c in chunks]

    if method == "chunk_directory":
        root = params.get("path")
        if not root:
            raise ValueError("chunk_directory requires path")
        ck = _chunker_from_params(params)
        results = ck.chunk_directory(
            str(root),
            glob=str(params.get("glob", "**/*")),
            exclude=list(params.get("exclude") or []),
            concurrency=int(params.get("concurrency", 10)),
            encoding=str(params.get("encoding", "utf-8")),
            include_hidden=bool(params.get("include_hidden", False)),
        )
        return [
            {
                "filepath": br.filepath,
                "error": br.error,
                "chunks": [chunk_to_dict(c) for c in br.chunks],
            }
            for br in results
        ]

    if method == "build_graph":
        raw_chunks = params.get("chunks")
        if not isinstance(raw_chunks, list):
            raise ValueError("build_graph requires chunks: list of chunk dicts")
        chunks = [chunk_from_dict(d) for d in raw_chunks if isinstance(d, dict)]
        min_occ = int(params.get("min_entity_occurrences", 1))
        graph = build_chunk_graph(chunks, min_entity_occurrences=min_occ)
        return graph.to_dict()

    if method == "semantic_chunk":
        filepath = str(params.get("filepath", "doc.md"))
        content = str(params.get("content", ""))
        backend = str(params.get("embed_backend", "mock"))
        ck = _chunker_from_params(params)
        if backend == "mock":
            embed_fn = _mock_embed_fn()
        else:
            raise ValueError(
                "semantic_chunk requires embed_backend='mock' over HTTP RPC, "
                "or use the Python API with a real semantic_embed_fn."
            )
        window = int(params.get("semantic_window", params.get("window", 3)))
        threshold = float(params.get("semantic_threshold", params.get("threshold", 0.3)))
        out = ck.semantic_chunk(
            filepath,
            content,
            embed_fn=embed_fn,
            window=window,
            threshold=threshold,
        )
        return [chunk_to_dict(c) for c in out]

    raise ValueError(f"unknown method: {method}")


class _MCPHandler(BaseHTTPRequestHandler):
    default_chunker_options: dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        if self.path not in ("/", "/rpc", "/mcp"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            err_body = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": str(e)},
                "id": None,
            }
            self._write_json(400, err_body)
            return

        if body.get("jsonrpc") != "2.0":
            bad_ver = {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "jsonrpc must be 2.0"},
                "id": body.get("id"),
            }
            self._write_json(400, bad_ver)
            return

        req_id = body.get("id")
        method = body.get("method")
        params = body.get("params")
        if not isinstance(params, dict):
            params = {}

        merged = {**self.default_chunker_options, **params}
        try:
            if not method:
                raise ValueError("missing method")
            result = _handle_tool(str(method), merged)
            self._write_json(200, {"jsonrpc": "2.0", "result": result, "id": req_id})
        except Exception as e:
            self._write_json(
                200,
                {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": req_id},
            )

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_mcp_server(host: str, port: int, *, config_path: Path | None = None) -> None:
    opts: dict[str, Any] = {}
    if config_path is not None and config_path.is_file():
        opts = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(opts, dict):
            opts = {}

    class Handler(_MCPHandler):
        default_chunker_options = opts

    server = HTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
