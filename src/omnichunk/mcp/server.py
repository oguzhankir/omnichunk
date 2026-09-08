"""Experimental JSON-RPC 2.0 over HTTP; this is not an MCP transport.

Filesystem tools are restricted to an operator-selected root. The historical
module path remains importable while the public command uses ``serve --rpc``.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import socket
import warnings
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from omnichunk import Chunker, build_chunk_graph
from omnichunk.chunker import _coerce_option_dict, _collect_directory_files
from omnichunk.serialization import chunk_from_dict, chunk_to_dict

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
    def embed(texts: list[str]) -> list[list[float]]:
        return [
            [
                float(len(text.encode("utf-8")) % 97),
                float((len(text.encode("utf-8")) // 97) % 97),
                0.0,
            ]
            for text in texts
        ]

    return embed


def _chunker_from_params(params: dict[str, Any]) -> Chunker:
    return Chunker(
        **_coerce_option_dict({k: v for k, v in params.items() if k not in _RESERVED_PARAMS})
    )


def _safe_path(path: str, allowed_root: Path) -> Path:
    root = allowed_root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("Requested path is outside the allowed root")
    return resolved


def _handle_tool(method: str, params: dict[str, Any], *, allowed_root: Path | None = None) -> Any:
    allowed_root = allowed_root if allowed_root is not None else Path.cwd()
    if method == "chunk_file":
        if not params.get("path"):
            raise ValueError("chunk_file requires path")
        path = _safe_path(str(params["path"]), allowed_root)
        chunks = _chunker_from_params(params).chunk_file(
            str(path), encoding=str(params.get("encoding", "utf-8"))
        )
        return [chunk_to_dict(chunk) for chunk in chunks]
    if method == "chunk_directory":
        if not params.get("path"):
            raise ValueError("chunk_directory requires path")
        root = _safe_path(str(params["path"]), allowed_root)
        pattern = str(params.get("glob", "**/*"))
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("glob must stay inside the allowed root")
        paths = (
            [root]
            if root.is_file()
            else _collect_directory_files(
                root,
                glob_pattern=pattern,
                exclude_patterns=list(params.get("exclude") or []),
                include_hidden=bool(params.get("include_hidden", False)),
            )
        )

        def process(path: Path) -> dict[str, Any]:
            try:
                chunks = _handle_tool(
                    "chunk_file", {**params, "path": str(path)}, allowed_root=allowed_root
                )
                return {"filepath": str(path), "error": None, "chunks": chunks}
            except Exception as exc:
                return {"filepath": str(path), "error": str(exc), "chunks": []}

        with ThreadPoolExecutor(
            max_workers=max(1, min(16, int(params.get("concurrency", 10))))
        ) as pool:
            return list(pool.map(process, paths))
    if method == "build_graph":
        raw_chunks = params.get("chunks")
        if not isinstance(raw_chunks, list) or not all(isinstance(d, dict) for d in raw_chunks):
            raise ValueError("build_graph requires chunks: list of chunk dicts")
        return build_chunk_graph(
            [chunk_from_dict(d) for d in raw_chunks],
            min_entity_occurrences=int(params.get("min_entity_occurrences", 1)),
        ).to_dict()
    if method == "semantic_chunk":
        if str(params.get("embed_backend", "mock")) != "mock":
            raise ValueError(
                "HTTP semantic_chunk supports only embed_backend='mock'; "
                "use the Python API for real embeddings"
            )
        chunks = _chunker_from_params(params).semantic_chunk(
            str(params.get("filepath", "doc.md")),
            str(params.get("content", "")),
            embed_fn=_mock_embed_fn(),
            window=int(params.get("semantic_window", params.get("window", 3))),
            threshold=float(params.get("semantic_threshold", params.get("threshold", 0.3))),
        )
        return [chunk_to_dict(chunk) for chunk in chunks]
    raise _MethodNotFoundError(method)


class _MethodNotFoundError(Exception):
    """Unknown RPC method."""


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _invalid_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


class _RPCHandler(BaseHTTPRequestHandler):
    default_chunker_options: dict[str, Any] = {}
    allowed_root: Path | None = None
    allowed_hosts: frozenset[str] = frozenset()
    auth_token: str | None = None
    max_body_bytes: int = 1_048_576
    request_timeout: float = 10.0

    def setup(self) -> None:
        self.request.settimeout(self.request_timeout)
        super().setup()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _error(self, status: int, code: int, message: str, req_id: Any = None) -> None:
        self._write_json(
            status, {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}
        )

    def _authorize(self) -> bool:
        hosts = self.headers.get_all("Host", [])
        bind_host, bind_port = cast("tuple[str, int]", self.server.server_address)[:2]
        allowed = self.allowed_hosts or frozenset({str(bind_host).lower()})
        if _is_loopback(str(bind_host)):
            allowed = allowed | {"localhost", "127.0.0.1", "::1"}
        try:
            if len(hosts) != 1:
                raise ValueError
            host = urlsplit("//" + hosts[0])
            if (
                host.hostname not in allowed
                or (host.port or 80) != bind_port
                or host.username is not None
                or host.password is not None
                or host.path
                or host.query
                or host.fragment
            ):
                raise ValueError
            origins = self.headers.get_all("Origin", [])
            if origins:
                origin = urlsplit(origins[0])
                if (
                    len(origins) != 1
                    or origin.scheme != "http"
                    or origin.netloc.lower() != hosts[0].lower()
                    or origin.path
                    or origin.query
                    or origin.fragment
                ):
                    raise ValueError
        except ValueError:
            self._error(403, -32000, "Untrusted Host or Origin")
            return False
        if not _is_loopback(str(bind_host)) and not self.auth_token:
            self._error(403, -32000, "Non-loopback RPC requires authentication")
            return False
        if self.auth_token:
            headers = self.headers.get_all("Authorization", [])
            expected = ("Bearer " + self.auth_token).encode("utf-8")
            if len(headers) != 1 or not hmac.compare_digest(headers[0].encode("utf-8"), expected):
                self._error(401, -32000, "Authentication required")
                return False
        return True

    def do_GET(self) -> None:
        if not self._authorize():
            return
        if self.path not in ("/", "/health"):
            self._error(404, -32601, "Unknown endpoint")
            return
        self._write_json(200, {"status": "ok", "protocol": "jsonrpc", "experimental": True})

    def do_POST(self) -> None:
        if not self._authorize():
            return
        if self.path not in ("/", "/rpc", "/mcp"):
            self._error(404, -32601, "Unknown endpoint")
            return
        lengths = self.headers.get_all("Content-Length", [])
        try:
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError
            length = int(lengths[0])
            if length < 0:
                raise ValueError
        except ValueError:
            self._error(
                400,
                -32600,
                "One valid Content-Length is required; transfer encoding is unsupported",
            )
            return
        if length > self.max_body_bytes:
            self._error(413, -32600, "Request body exceeds configured limit")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                self._error(400, -32600, "Incomplete request body")
                return
        except TimeoutError:
            self._error(408, -32600, "Request body timed out")
            return
        try:
            body = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
        except (ValueError, RecursionError):
            self._error(400, -32700, "Invalid JSON body")
            return
        if not isinstance(body, dict):
            self._error(400, -32600, "Request must be a JSON object")
            return
        req_id = body.get("id")
        if (
            body.get("jsonrpc") != "2.0"
            or not isinstance(body.get("method"), str)
            or not body["method"]
            or isinstance(req_id, (bool, list, dict))
        ):
            self._error(400, -32600, "Invalid JSON-RPC request", req_id=None)
            return
        params = body.get("params", {})
        if not isinstance(params, dict):
            self._error(400, -32602, "params must be an object", req_id)
            return
        try:
            result = _handle_tool(
                body["method"],
                {**self.default_chunker_options, **params},
                allowed_root=self.allowed_root,
            )
        except _MethodNotFoundError:
            self._error(200, -32601, "Method not found", req_id)
            return
        except Exception as exc:
            self._error(200, -32000, str(exc), req_id)
            return
        if "id" not in body:
            self.send_response(204)
            self.end_headers()
            return
        self._write_json(200, {"jsonrpc": "2.0", "result": result, "id": req_id})

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


# Import compatibility only: the service does not implement MCP initialization.
_MCPHandler = _RPCHandler


def create_rpc_server(
    host: str = "127.0.0.1",
    port: int = 3333,
    *,
    config_path: Path | None = None,
    allowed_root: Path | None = None,
    auth_token: str | None = None,
    allowed_hosts: Sequence[str] | None = None,
    max_body_bytes: int = 1_048_576,
    request_timeout: float = 10.0,
) -> HTTPServer:
    """Construct a bounded HTTP server without starting its request loop."""
    if not _is_loopback(host) and not auth_token:
        raise ValueError("Non-loopback RPC requires an authentication token")
    if max_body_bytes < 1 or request_timeout <= 0:
        raise ValueError("Body size and request timeout must be positive")
    root = (allowed_root if allowed_root is not None else Path.cwd()).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("allowed_root must be a directory")
    opts: dict[str, Any] = {}
    if config_path is not None:
        opts = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(opts, dict):
            raise ValueError("RPC config must be a JSON object")
        _chunker_from_params(opts)

    class Handler(_RPCHandler):
        pass

    Handler.default_chunker_options = opts
    Handler.allowed_root = root
    Handler.auth_token = auth_token
    Handler.allowed_hosts = frozenset(item.lower() for item in (allowed_hosts or [host]))
    Handler.max_body_bytes = max_body_bytes
    Handler.request_timeout = request_timeout
    if ":" in host:

        class IPv6Server(HTTPServer):
            address_family = socket.AF_INET6

        return IPv6Server((host, port), Handler)
    return HTTPServer((host, port), Handler)


def run_rpc_server(host: str = "127.0.0.1", port: int = 3333, **options: Any) -> None:
    server = create_rpc_server(host, port, **options)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def run_mcp_server(
    host: str, port: int, *, config_path: Path | None = None, **options: Any
) -> None:
    """Deprecated alias for the experimental JSON-RPC service."""
    warnings.warn(
        "run_mcp_server is deprecated; use run_rpc_server. This is JSON-RPC, not MCP.",
        DeprecationWarning,
        stacklevel=2,
    )
    run_rpc_server(host, port, config_path=config_path, **options)
