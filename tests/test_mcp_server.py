from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Generator
from http.server import HTTPServer
from pathlib import Path

import pytest

from omnichunk.mcp.server import _MCPHandler  # noqa: PLC2701

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def _raw_post(url: str, body_bytes: bytes) -> dict:
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def _get_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}


# ---------------------------------------------------------------------------
# Fixture: ephemeral MCP server on a random port
# ---------------------------------------------------------------------------


@pytest.fixture()
def mcp_url() -> Generator[str, None, None]:
    server = HTTPServer(("127.0.0.1", 0), _MCPHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=5.0)


# ---------------------------------------------------------------------------
# (a) chunk_file returns correct chunk structure for a Python snippet
# ---------------------------------------------------------------------------


def test_mcp_jsonrpc_chunk_file(tmp_path: Path, mcp_url: str) -> None:
    f = tmp_path / "hi.py"
    f.write_text("def f():\n    return 42\n", encoding="utf-8")
    body = _post_json(
        mcp_url + "/",
        {
            "jsonrpc": "2.0",
            "method": "chunk_file",
            "params": {"path": str(f), "max_chunk_size": 2000},
            "id": 1,
        },
    )
    assert body.get("id") == 1
    assert "result" in body, body
    chunks = body["result"]
    assert isinstance(chunks, list) and chunks

    chunk = chunks[0]
    assert isinstance(chunk.get("text"), str) and chunk["text"]
    assert "byte_range" in chunk
    assert "return 42" in "".join(c["text"] for c in chunks)


# ---------------------------------------------------------------------------
# (b) chunk_directory handles empty directory
# ---------------------------------------------------------------------------


def test_mcp_chunk_directory_empty(tmp_path: Path, mcp_url: str) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    body = _post_json(
        mcp_url + "/rpc",
        {
            "jsonrpc": "2.0",
            "method": "chunk_directory",
            "params": {"path": str(empty_dir), "glob": "**/*.py"},
            "id": 2,
        },
    )
    assert "result" in body, body
    assert isinstance(body["result"], list)
    assert body["result"] == []


# ---------------------------------------------------------------------------
# (c) build_graph returns at least one node for code with entities
# ---------------------------------------------------------------------------


def test_mcp_build_graph_has_nodes(tmp_path: Path, mcp_url: str) -> None:
    code = (
        "import os\n\n"
        "class MyClass:\n"
        "    value = 42\n\n"
        "    def method_one(self):\n"
        "        return MyClass.value\n\n"
        "    def method_two(self):\n"
        "        return MyClass.value + 1\n\n"
        "def helper():\n"
        "    return MyClass().method_one()\n"
    )
    f = tmp_path / "code.py"
    f.write_text(code, encoding="utf-8")

    chunk_resp = _post_json(
        mcp_url + "/",
        {
            "jsonrpc": "2.0",
            "method": "chunk_file",
            "params": {
                    "path": str(f),
                    "max_chunk_size": 80,
                    "min_chunk_size": 5,
                    "size_unit": "chars",
                },
            "id": 10,
        },
    )
    assert "result" in chunk_resp, chunk_resp
    chunk_dicts = chunk_resp["result"]
    assert chunk_dicts, "need at least one chunk to build a graph"

    graph_resp = _post_json(
        mcp_url + "/",
        {
            "jsonrpc": "2.0",
            "method": "build_graph",
            "params": {"chunks": chunk_dicts, "min_entity_occurrences": 1},
            "id": 11,
        },
    )
    assert "result" in graph_resp, graph_resp
    result = graph_resp["result"]
    assert "nodes" in result
    assert "chunk_count" in result
    assert result["chunk_count"] >= 1
    assert len(result["nodes"]) >= 1, f"expected nodes, got: {result['nodes']}"


# ---------------------------------------------------------------------------
# (d) semantic_chunk with user-supplied embed function stub returns valid chunks
# ---------------------------------------------------------------------------


def test_mcp_semantic_chunk_user_embed_stub(mcp_url: str) -> None:
    text = (
        "First paragraph with some content.\n\n"
        "Second paragraph that has different ideas.\n\n"
        "Third block here with yet more text.\n\n"
        "Fourth section to ensure multiple splits happen.\n"
    )
    body = _post_json(
        mcp_url + "/mcp",
        {
            "jsonrpc": "2.0",
            "method": "semantic_chunk",
            "params": {
                "filepath": "doc.md",
                "content": text,
                "embed_backend": "mock",
                "semantic_threshold": 0.0,
            },
            "id": 4,
        },
    )
    assert "result" in body, body
    chunks = body["result"]
    assert isinstance(chunks, list) and chunks
    for chunk in chunks:
        assert isinstance(chunk.get("text"), str) and chunk["text"].strip()
        assert "byte_range" in chunk


# ---------------------------------------------------------------------------
# (e) invalid tool name returns JSON-RPC error with code -32601
# ---------------------------------------------------------------------------


def test_mcp_invalid_tool_returns_32601(mcp_url: str) -> None:
    body = _post_json(
        mcp_url + "/",
        {"jsonrpc": "2.0", "method": "no_such_tool", "params": {}, "id": 5},
    )
    assert "error" in body, body
    assert body["error"]["code"] == -32601
    assert body.get("id") == 5


# (legacy alias kept for backwards-compat with pre-existing test name)
def test_mcp_unknown_method_error(mcp_url: str) -> None:
    body = _post_json(
        mcp_url + "/",
        {"jsonrpc": "2.0", "method": "no_such", "params": {}, "id": 3},
    )
    assert "error" in body
    assert body["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# (f) malformed JSON body returns error code -32700
# ---------------------------------------------------------------------------


def test_mcp_malformed_json_returns_32700(mcp_url: str) -> None:
    body = _raw_post(mcp_url + "/", b"{not valid json!!!")
    assert "error" in body, body
    assert body["error"]["code"] == -32700


# ---------------------------------------------------------------------------
# (g) server binds to a random port and health endpoint returns 200 OK
# ---------------------------------------------------------------------------


def test_mcp_health_endpoint_200(mcp_url: str) -> None:
    status, body = _get_json(mcp_url + "/")
    assert status == 200
    assert body.get("status") == "ok"


def test_mcp_health_endpoint_dedicated_path(mcp_url: str) -> None:
    status, body = _get_json(mcp_url + "/health")
    assert status == 200
    assert body.get("status") == "ok"


# ---------------------------------------------------------------------------
# (h) concurrent requests do not raise thread-safety errors
# ---------------------------------------------------------------------------


def test_mcp_concurrent_requests(tmp_path: Path, mcp_url: str) -> None:
    f = tmp_path / "work.py"
    f.write_text("x = 1\n" * 20, encoding="utf-8")
    url = mcp_url + "/"
    payload = {
        "jsonrpc": "2.0",
        "method": "chunk_file",
        "params": {"path": str(f), "max_chunk_size": 2000},
        "id": 99,
    }

    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            for _ in range(5):
                body = _post_json(url, payload)
                assert "result" in body, body
                assert isinstance(body["result"], list)
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)
        assert not t.is_alive(), "thread did not finish within timeout"

    assert errors == [], f"concurrent errors: {errors}"


# ---------------------------------------------------------------------------
# (original) semantic_chunk mock — kept for coverage continuity
# ---------------------------------------------------------------------------


def test_mcp_semantic_chunk_mock(mcp_url: str) -> None:
    text = "First paragraph.\n\nSecond paragraph with more text.\n\nThird block here."
    body = _post_json(
        mcp_url + "/",
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
