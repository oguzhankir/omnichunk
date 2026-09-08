from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnichunk.cli import main


def test_cli_token_budget_requires_explicit_tokenizer(tmp_path: Path, capsys) -> None:
    source = tmp_path / "doc.txt"
    source.write_text("Some prose.")
    assert main([str(source), "--size-unit", "tokens"]) == 2
    assert "--tokenizer" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--rpc", "--mcp"])
def test_cli_rpc_name_and_deprecated_alias(monkeypatch, capsys, flag) -> None:
    import omnichunk.mcp.server as server

    calls = []
    monkeypatch.setattr(server, "run_rpc_server", lambda *args, **kwargs: calls.append(kwargs))
    assert main(["serve", flag]) == 0
    output = capsys.readouterr()
    assert "JSON-RPC" in output.out
    assert ("deprecated" in output.err) == (flag == "--mcp")
    assert calls[0]["allowed_root"] == Path.cwd()


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


def test_cli_accepts_nws_backend_flag(tmp_path: Path, capsys) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("def ping():\n    return 'pong'\n", encoding="utf-8")

    exit_code = main(
        [
            str(file_path),
            "--format",
            "json",
            "--size-unit",
            "chars",
            "--max-size",
            "40",
            "--nws-backend",
            "python",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload


def test_cli_invalid_explicit_sizes_return_error(tmp_path: Path, capsys) -> None:
    source = tmp_path / "file.txt"
    source.write_text("content")
    assert main([str(source), "--max-size", "10", "--min-size", "11"]) == 2
    assert "min_chunk_size" in capsys.readouterr().err


def test_cli_server_requires_rpc_and_reports_startup_errors(monkeypatch, capsys) -> None:
    import omnichunk.mcp.server as server

    assert main(["serve"]) == 2
    assert "--rpc" in capsys.readouterr().err

    def fail(*args, **kwargs):
        raise ValueError("Authentication token is missing")

    monkeypatch.setattr(server, "run_rpc_server", fail)
    assert main(["serve", "--rpc"]) == 2
    assert "RPC startup failed" in capsys.readouterr().err


@pytest.mark.parametrize("output_format", ["json", "jsonl", "csv"])
@pytest.mark.parametrize("write_file", [False, True])
def test_cli_export_formats_to_stdout_and_files(
    tmp_path: Path, capsys, output_format, write_file
) -> None:
    import csv
    import io

    source = tmp_path / "document.txt"
    source.write_text("A useful source sentence.\nSecond sentence.")
    output = tmp_path / f"chunks.{output_format}"
    arguments = [str(source), "--format", output_format]
    if write_file:
        arguments.extend(["--output", str(output)])
    assert main(arguments) == 0
    stdout = capsys.readouterr().out
    payload = output.read_text() if write_file else stdout
    if write_file:
        assert stdout == ""
    if output_format == "csv":
        rows = list(csv.DictReader(io.StringIO(payload)))
    elif output_format == "jsonl":
        rows = [json.loads(line) for line in payload.splitlines()]
    else:
        rows = json.loads(payload)
    assert rows
    assert "useful source sentence" in "".join(row["text"] for row in rows)


@pytest.mark.parametrize("metrics", ["all", "reconstruction,coverage"])
@pytest.mark.parametrize("with_source", [False, True])
def test_cli_eval_export_roundtrip(tmp_path: Path, capsys, metrics, with_source) -> None:
    source = tmp_path / "source.txt"
    source.write_text("First sentence.\nSecond sentence.\n")
    chunks = tmp_path / "chunks.jsonl"
    output = tmp_path / "evaluation.json"
    assert main([str(source), "--format", "jsonl", "--output", str(chunks)]) == 0
    chunks.write_text(chunks.read_text() + "\n")
    arguments = ["eval", str(chunks), "--metrics", metrics]
    if with_source:
        arguments.extend(["--source", str(source), "--output", str(output)])
    assert main(arguments) == 0
    stdout = capsys.readouterr().out
    report = json.loads(output.read_text() if with_source else stdout)
    assert "aggregate" in report
    if with_source:
        assert report["aggregate"]["reconstruction"] == 1.0


def test_cli_missing_input_and_missing_eval_file(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.txt"
    assert main([str(missing)]) == 2
    assert "Target does not exist" in capsys.readouterr().err
    assert main(["eval", str(missing)]) == 2
    assert "File does not exist" in capsys.readouterr().err


def test_cli_empty_directory_and_partial_read_errors(tmp_path: Path, capsys) -> None:
    assert main([str(tmp_path), "--stats"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total_chunks"] == 0
    (tmp_path / "valid.txt").write_text("Valid text.")
    (tmp_path / "invalid.txt").write_bytes(b"\xff")
    assert main([str(tmp_path), "--stats"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["failed_files"] == 1
    assert report["total_chunks"] > 0


def test_cli_bad_file_reports_error_without_traceback(tmp_path: Path, capsys) -> None:
    source = tmp_path / "bad.txt"
    source.write_bytes(b"\xff")
    assert main([str(source)]) == 1
    output = capsys.readouterr()
    assert "bad.txt" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("value", ["", "-2", "-0.1", "x", "1.x"])
def test_cli_invalid_overlap_is_argument_error(tmp_path: Path, value) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Source text.")
    with pytest.raises(SystemExit) as error:
        main([str(source), f"--overlap={value}"])
    assert error.value.code == 2


@pytest.mark.parametrize("value", ["2", "0.2"])
def test_cli_overlap_and_semantic_debug_flags(tmp_path: Path, capsys, value) -> None:
    source = tmp_path / "source.txt"
    source.write_text(
        "Cooking ingredients and garlic. Cooking sauce with basil.\n\n"
        "Galaxy stars in the universe. Galactic astronomy and planets."
    )
    assert main([str(source), "--max-size", "40", "--overlap", value, "--semantic-debug"]) == 0
    output = capsys.readouterr()
    chunks = json.loads(output.out)
    assert chunks
    assert "gap[" in output.err


def test_cli_reads_sys_argv(monkeypatch, tmp_path: Path, capsys) -> None:
    import sys

    source = tmp_path / "source.txt"
    source.write_text("Source text.")
    monkeypatch.setattr(sys, "argv", ["omnichunk", str(source)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)
