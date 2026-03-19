from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_SCRIPT = ROOT / "benchmarks" / "run_html_report.py"


def test_run_html_report_importable_without_running_main() -> None:
    assert "if __name__" in HTML_SCRIPT.read_text(encoding="utf-8")


def test_run_html_report_generates_file(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    result = subprocess.run(
        [
            sys.executable,
            str(HTML_SCRIPT),
            "--output",
            str(out),
            "--repeat",
            "1",
            "--scenarios",
            "sample_json",
        ],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "omnichunk" in body
    assert "Throughput" in body
    assert "Quality" in body


def test_run_html_report_raw_json_valid(tmp_path: Path) -> None:
    out = tmp_path / "rep.html"
    subprocess.run(
        [
            sys.executable,
            str(HTML_SCRIPT),
            "--output",
            str(out),
            "--repeat",
            "1",
            "--scenarios",
            "sample_json",
        ],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
    )
    body = out.read_text(encoding="utf-8")
    m = re.search(r'<pre id="omnichunk-raw-json">(.*?)</pre>', body, re.DOTALL)
    assert m
    raw = html.unescape(m.group(1).strip())
    data = json.loads(raw)
    assert "throughput" in data
    assert "quality" in data
