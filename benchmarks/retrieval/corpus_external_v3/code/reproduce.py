"""Run the data importer, then fail if its canonical manifest hashes drift."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--include-validation", action="store_true", help="Only use after final freeze")
args = parser.parse_args()
root = Path(__file__).resolve().parent
expected = json.loads((root / "expected-manifests.json").read_text())
subprocess.run(
    [sys.executable, str(root / "build.py")]
    + ([] if args.include_validation else ["--development-only"]),
    check=True,
)
for split, directory in [("dev", "development")] + (
    [("test", "private-validation")] if args.include_validation else []
):
    actual = hashlib.sha256((root / directory / "manifest.json").read_bytes()).hexdigest()
    if actual != expected[split]:
        raise ValueError(f"{split} manifest changed: {actual} != {expected[split]}")
    print(split, actual)
