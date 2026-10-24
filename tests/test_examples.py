"""Keep the documented offline workflows executable against the current API."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("script", sorted(EXAMPLES.glob("[0-9][0-9]_*.py")), ids=lambda p: p.stem)
def test_offline_example(script: Path, tmp_path: Path) -> None:
    if script.name.startswith("09_"):
        pytest.importorskip("numpy")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
