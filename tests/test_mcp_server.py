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
def mcp_url(tmp_path: Path) -> Generator[str, None, None]:
    class Handler(_MCPHandler):
        allowed_root = tmp_path
        max_body_bytes = 65_536
        request_timeout = 0.2

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
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


def test_rpc_denies_paths_outside_allowed_root(tmp_path: Path, mcp_url: str) -> None:
    outside = tmp_path.parent / "outside-rpc.txt"
    outside.write_text("private content")
    response = _post_json(
        mcp_url,
        {"jsonrpc": "2.0", "method": "chunk_file", "params": {"path": str(outside)}, "id": 1},
    )
    assert "result" not in response
    assert "allowed root" in response["error"]["message"]


def test_rpc_denies_symlink_escape(tmp_path: Path, mcp_url: str) -> None:
    outside = tmp_path.parent / "outside-symlink.txt"
    outside.write_text("private content")
    link = tmp_path / "linked.txt"
    link.symlink_to(outside)
    for method in ("chunk_file", "chunk_directory"):
        response = _post_json(
            mcp_url,
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": {"path": str(link if method == "chunk_file" else tmp_path)},
                "id": 1,
            },
        )
        assert "private content" not in json.dumps(response)
        assert "error" in json.dumps(response)


@pytest.mark.parametrize(
    "headers", [{"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Origin": "null"}]
)
def test_rpc_rejects_untrusted_host_origin(mcp_url: str, headers: dict) -> None:
    request = urllib.request.Request(mcp_url, data=b"{}", headers=headers, method="POST")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 403


def test_rpc_rejects_oversized_body(mcp_url: str) -> None:
    request = urllib.request.Request(mcp_url, data=b" " * 65_537, method="POST")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 413


@pytest.mark.parametrize("body", [b"[]", b"null", b"42", b'"string"'])
def test_rpc_rejects_nonobject_json(mcp_url: str, body: bytes) -> None:
    assert _raw_post(mcp_url, body)["error"]["code"] == -32600


def test_public_rpc_requires_authentication_before_binding() -> None:
    from omnichunk.mcp.server import create_rpc_server

    with pytest.raises(ValueError, match="auth"):
        create_rpc_server("0.0.0.0", 0)


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": "-1"},
        {"Content-Length": "nope"},
        {"Content-Length": "0", "Transfer-Encoding": "chunked"},
    ],
)
def test_rpc_rejects_invalid_framing(mcp_url: str, headers: dict) -> None:
    import http.client
    from urllib.parse import urlsplit

    url = urlsplit(mcp_url)
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
    try:
        connection.request("POST", "/rpc", body=b"", headers=headers)
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read())["error"]["code"] == -32600
    finally:
        connection.close()


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"jsonrpc": "1.0", "method": "build_graph", "id": 1}, -32600),
        ({"jsonrpc": "2.0", "method": 1, "id": 1}, -32600),
        ({"jsonrpc": "2.0", "method": "build_graph", "id": []}, -32600),
        ({"jsonrpc": "2.0", "method": "build_graph", "params": [], "id": 1}, -32602),
        ({"jsonrpc": "2.0", "method": "chunk_file", "params": {}, "id": 1}, -32000),
        ({"jsonrpc": "2.0", "method": "chunk_directory", "params": {}, "id": 1}, -32000),
        ({"jsonrpc": "2.0", "method": "build_graph", "params": {"chunks": [3]}, "id": 1}, -32000),
        (
            {
                "jsonrpc": "2.0",
                "method": "semantic_chunk",
                "params": {"embed_backend": "real"},
                "id": 1,
            },
            -32000,
        ),
    ],
)
def test_rpc_rejects_invalid_requests(mcp_url: str, payload: dict, code: int) -> None:
    assert _post_json(mcp_url, payload)["error"]["code"] == code


def test_rpc_valid_notification_has_no_response_body(mcp_url: str) -> None:
    body = json.dumps(
        {"jsonrpc": "2.0", "method": "build_graph", "params": {"chunks": []}}
    ).encode()
    request = urllib.request.Request(mcp_url, data=body)
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 204
        assert response.read() == b""


def test_rpc_invalid_utf8_is_parse_error(mcp_url: str) -> None:
    assert _raw_post(mcp_url, b'"\xff"')["error"]["code"] == -32700


def test_rpc_root_relative_file_and_glob_restriction(tmp_path: Path, mcp_url: str) -> None:
    (tmp_path / "document.txt").write_text("Readable source.")
    response = _post_json(
        mcp_url,
        {"jsonrpc": "2.0", "method": "chunk_file", "params": {"path": "document.txt"}, "id": 1},
    )
    assert response["result"][0]["text"] == "Readable source."
    response = _post_json(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "method": "chunk_directory",
            "params": {"path": ".", "glob": "../*"},
            "id": 1,
        },
    )
    assert "allowed root" in response["error"]["message"]


def test_rpc_authentication_and_same_origin(tmp_path: Path) -> None:
    from omnichunk.mcp.server import create_rpc_server

    server = create_rpc_server("127.0.0.1", 0, allowed_root=tmp_path, auth_token="test-token")
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert _get_json(base)[0] == 401
        request = urllib.request.Request(
            base + "/health", headers={"Authorization": "Bearer test-token", "Origin": base}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_rpc_server_configuration_validation(tmp_path: Path) -> None:
    from omnichunk.mcp.server import create_rpc_server

    for options in ({"max_body_bytes": 0}, {"request_timeout": 0}):
        with pytest.raises(ValueError, match="positive"):
            create_rpc_server(port=0, **options)
    config = tmp_path / "config.json"
    config.write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        create_rpc_server(port=0, config_path=config)
    with pytest.raises(ValueError, match="directory"):
        create_rpc_server(port=0, allowed_root=config)
    config.write_text('{"max_chunk_size": 200, "size_unit": "chars"}')
    server = create_rpc_server(port=0, config_path=config, allowed_root=tmp_path)
    try:
        assert server.RequestHandlerClass.default_chunker_options["max_chunk_size"] == 200
    finally:
        server.server_close()


def test_rpc_lifecycle_and_legacy_warning(monkeypatch) -> None:
    from omnichunk.mcp import server as module

    closed = []

    class Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            closed.append(True)

    monkeypatch.setattr(module, "create_rpc_server", lambda *args, **kwargs: Server())
    with pytest.warns(DeprecationWarning, match="JSON-RPC, not MCP"):
        module.run_mcp_server("127.0.0.1", 0)
    assert closed == [True]


def test_rpc_request_body_timeout(mcp_url: str) -> None:
    import socket
    from urllib.parse import urlsplit

    url = urlsplit(mcp_url)
    with socket.create_connection((url.hostname, url.port), timeout=5) as connection:
        request = (
            f"POST /rpc HTTP/1.1\r\nHost: {url.netloc}\r\nContent-Length: 100\r\n\r\n{{"
        ).encode()
        connection.sendall(request)
        assert b"408" in connection.recv(4096).split(b"\r\n", 1)[0]


def test_rpc_unknown_endpoint(mcp_url: str) -> None:
    assert _get_json(mcp_url + "/missing")[0] == 404
    assert _raw_post(mcp_url + "/missing", b"{}")["error"]["code"] == -32601


@pytest.mark.parametrize(
    "raw",
    [b'{"jsonrpc":"2.0","method":"missing","id":NaN}', b"[" * 10000 + b"]" * 10000],
    ids=["nonfinite", "deep-json"],
)
def test_rpc_nonstandard_or_excessively_nested_json_is_parse_error(
    mcp_url: str, raw: bytes
) -> None:
    assert _raw_post(mcp_url, raw)["error"]["code"] == -32700
