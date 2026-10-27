"""Fingerprint this experiment's installed distributions without inspecting secrets.

Run once from the experiment virtualenv. Package digests hash the installed bytes
enumerated by importlib.metadata; they are not wheel/archive hashes. Generated
RECORD metadata and bytecode are included if enumerated by the distribution.
Editable source files are recorded separately when their local project is known.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "environment"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest_manifest(files: dict[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def command(arguments: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {"available": False, "error_type": type(exc).__name__}
    return {"available": True, "returncode": result.returncode, "stdout": result.stdout}


def editable_source(distribution: importlib.metadata.Distribution) -> dict[str, object] | None:
    raw = distribution.read_text("direct_url.json")
    if not raw:
        return None
    info = json.loads(raw)
    if not info.get("dir_info", {}).get("editable", False):
        return None
    location = urlparse(info.get("url", ""))
    if location.scheme != "file" or location.netloc not in ("", "localhost"):
        return {"editable": True, "local_source_available": False}
    directory = Path(unquote(location.path))
    files = {
        str(path.relative_to(directory)): digest_file(path)
        for path in sorted((directory / "src").rglob("*.py"))
        if path.is_file()
    }
    return {
        "editable": True,
        "local_source_available": bool(files),
        "source_files": files,
        "source_manifest_sha256": digest_manifest(files),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    packages = []
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: (item.metadata["Name"].casefold(), item.version),
    ):
        files = {}
        missing = []
        for entry in sorted(distribution.files or [], key=str):
            path = Path(distribution.locate_file(entry))
            if path.is_file():
                files[str(entry)] = digest_file(path)
            else:
                missing.append(str(entry))
        record = {
            "name": distribution.metadata["Name"],
            "version": distribution.version,
            "files": files,
            "missing_files": missing,
            "installed_file_manifest_sha256": digest_manifest(files),
        }
        editable = editable_source(distribution)
        if editable:
            record["editable_source"] = editable
        packages.append(record)
    summary = [
        {key: package[key] for key in ("name", "version", "installed_file_manifest_sha256")}
        | {"file_count": len(package["files"]), "missing_count": len(package["missing_files"])}
        for package in packages
    ]
    manifest = {
        "schema_version": 1,
        "scope": (
            "SHA-256 of installed bytes enumerated by importlib.metadata, including RECORD "
            "and bytecode when listed; package-root digests hash canonical path/hash JSON. "
            "These are installed-file hashes, not wheel archive or upstream release hashes."
        ),
        "packages": packages,
    }
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (OUTPUT / "installed-package-hashes.json").write_text(payload)
    (OUTPUT / "installed-package-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    (OUTPUT / "installed-requirements.txt").write_text(
        "\n".join(f"{package['name']}=={package['version']}" for package in packages) + "\n"
    )
    runtime = {
        "schema_version": 1,
        "python": sys.version,
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "lscpu": command(["lscpu", "--json"]),
        "git": command(["git", "--version"]),
        "installed_package_manifest_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "capture_script_sha256": digest_file(Path(__file__)),
    }
    (OUTPUT / "runtime.json").write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "packages": len(packages),
        "installed_files": sum(len(package["files"]) for package in packages),
        "missing_files": sum(len(package["missing_files"]) for package in packages),
        "installed_package_manifest_sha256": runtime["installed_package_manifest_sha256"],
        "output_directory": str(OUTPUT),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
