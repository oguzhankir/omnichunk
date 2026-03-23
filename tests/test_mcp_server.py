from __future__ import annotations

import json
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from omnichunk.mcp.server import _MCPHandler


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_mcp_jsonrpc_chunk_file(tmp_path: Path) -> None:
    f = tmp_path / "hi.py"
    f.write_text("def f():\n    return 42\n", encoding="utf-8")
    server = HTTPServer(("127.0.0.1", 0), _MCPHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{port}/"
        body = _post_json(
            url,
            {
                "jsonrpc": "2.0",
                "method": "chunk_file",
                "params": {"path": str(f), "max_chunk_size": 2000},
                "id": 1,
            },
        )
        assert body.get("id") == 1
        assert "result" in body
        assert isinstance(body["result"], list)
        assert body["result"]
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_semantic_chunk_mock(tmp_path: Path) -> None:
    server = HTTPServer(("127.0.0.1", 0), _MCPHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{port}/"
        text = "First paragraph.\n\nSecond paragraph with more text.\n\nThird block here."
        body = _post_json(
            url,
            {
                "jsonrpc": "2.0",
                "method": "semantic_chunk",
                "params": {
                    "filepath": "p.md",
                    "content": text,
                    "embed_backend": "mock",
                    "semantic_threshold": 0.0,
                },
                "id": 2,
            },
        )
        assert "result" in body
        assert isinstance(body["result"], list)
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_unknown_method_error() -> None:
    server = HTTPServer(("127.0.0.1", 0), _MCPHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{port}/"
        body = _post_json(
            url,
            {"jsonrpc": "2.0", "method": "no_such", "params": {}, "id": 3},
        )
        assert "error" in body
    finally:
        server.shutdown()
        server.server_close()
