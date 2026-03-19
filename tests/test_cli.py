from __future__ import annotations

import json
from pathlib import Path

from omnichunk.cli import main


def test_cli_outputs_jsonl_for_file(tmp_path: Path, capsys) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("def ping():\n    return 'pong'\n", encoding="utf-8")

    exit_code = main(
        [
            str(file_path),
            "--format",
            "jsonl",
            "--size-unit",
            "chars",
            "--max-size",
            "40",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0

    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert lines
    first = json.loads(lines[0])
    assert first["context"]["filepath"] == str(file_path)


def test_cli_stats_for_directory(tmp_path: Path, capsys) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (src_dir / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    exit_code = main(
        [
            str(src_dir),
            "--glob",
            "**/*.py",
            "--size-unit",
            "chars",
            "--max-size",
            "48",
            "--stats",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0

    payload = json.loads(captured.out)
    assert payload["total_chunks"] >= 2
    assert payload["size_unit"] == "chars"
    assert payload["failed_files"] == 0
