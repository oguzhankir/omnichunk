"""Download and verify pinned corpus inputs (no scoring or model downloads)."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("corpus", choices=["code", "turkish"])
args = parser.parse_args()
root = Path(__file__).resolve().parent / args.corpus
record = json.loads(
    (root / ("upstream-audit.json" if args.corpus == "code" else "upstream.json")).read_text()
)
upstream = root / "upstream"
upstream.mkdir(exist_ok=True)
for item in record["files"]:
    if args.corpus == "code":
        url = f"https://huggingface.co/datasets/{record['dataset']}/resolve/{record['revision']}/{item['upstream_path']}"
        filename = Path(item["upstream_path"]).name
        size = item["size_bytes"]
    else:
        url = item["url"]
        filename = item["path"]
        size = item["bytes"]
    destination = upstream / filename
    data = (
        destination.read_bytes()
        if destination.exists()
        else urllib.request.urlopen(url, timeout=120).read()
    )
    if len(data) != size or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError(f"Pinned input checksum/size mismatch: {filename}")
    destination.write_bytes(data)
    print(filename, item["sha256"])
