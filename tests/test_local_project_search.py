"""Exercise the offline project search on real source bytes."""

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "15_search_local_project.py"


def test_skipped_directories_are_not_traversed(tmp_path: Path, monkeypatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("project_scan", SCRIPT)
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    for folder in (".cache", "venv", "env", "node_modules", "build", "dist", "__pycache__", "src"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "content.py").write_text("backup", encoding="utf-8")
    (tmp_path / ".hidden.py").write_text("backup", encoding="utf-8")
    try:
        (tmp_path / "src" / "link.py").symlink_to(tmp_path / "src" / "content.py")
        (tmp_path / "linked-dir").symlink_to(tmp_path / "src", target_is_directory=True)
    except OSError:
        pass  # Symlink creation may require elevated privileges on Windows.
    visited = []
    original_walk = os.walk

    def observe_walk(*args, **kwargs):
        for directory, dirs, files in original_walk(*args, **kwargs):
            visited.append(Path(directory).relative_to(tmp_path))
            yield directory, dirs, files

    monkeypatch.setattr(demo.os, "walk", observe_walk)
    assert demo.load_sources(tmp_path) == {"src/content.py": "backup"}
    assert set(visited) == {Path("."), Path("src")}


def test_searches_project_and_cites_utf8_crlf_bytes(tmp_path: Path) -> None:
    raw = "## Bilgi\r\n\r\nYedekler 30 gün saklanır.\r\n".encode()
    (tmp_path / "notice.md").write_bytes(raw)
    (tmp_path / "service.py").write_text('"""Yedekler policy."""\n', encoding="utf-8")
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "hidden.md").write_text("Yedekler", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(tmp_path), "--question", "Yedekler"],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    assert "Indexed 2 file(s)" in result.stdout
    assert "service.py" in result.stdout and "hidden.md" not in result.stdout
    match = re.search(r"notice\.md, lines (\d+)-(\d+), bytes (\d+):(\d+)", result.stdout)
    assert match is not None
    first, last, start, end = map(int, match.groups())
    excerpt = raw[start:end]
    assert "Yedekler 30 gün saklanır." in excerpt.decode()
    assert first == raw[:start].count(b"\n") + 1
    assert last == first + excerpt.rstrip(b"\n").count(b"\n")


def test_no_matching_source_does_not_invent_an_answer(tmp_path: Path) -> None:
    (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(tmp_path), "--question", "unfindable"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "No matching source excerpts" in result.stdout


def test_answer_generation_sends_only_selected_excerpts(monkeypatch) -> None:
    import importlib.util
    import io
    import json

    spec = importlib.util.spec_from_file_location("project_search", SCRIPT)
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    sources = {"public.md": "# Backup\n\nBackups expire after 30 days.\n", "private.txt": "secret"}
    results = demo.search(sources, "backups expire")
    observed = {}

    def fake_urlopen(request, timeout):
        observed["body"] = json.loads(request.data)
        observed["url"] = request.full_url
        observed["timeout"] = timeout
        return io.BytesIO(
            json.dumps(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "30 days [public.md]"}],
                        }
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr(demo, "urlopen", fake_urlopen)
    assert demo.generate_answer("backups expire", results, "test-key") == "30 days [public.md]"
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert "public.md" in observed["body"]["input"]
    assert "secret" not in observed["body"]["input"]
    assert observed["timeout"] == 30
