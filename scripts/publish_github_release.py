"""Publish a GitHub release for validated tag artifacts from Actions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ["RELEASE_TAG"]
    notes = Path(f".github/release-notes-{tag.removeprefix('v')}.md")
    if not notes.is_file():
        raise ValueError("Prepare reviewed release notes for this version before publishing")
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository], capture_output=True
    )
    if existing.returncode:
        gh(
            "release",
            "create",
            tag,
            "--verify-tag",
            "--repo",
            repository,
            "--title",
            f"OmniChunk {tag}",
            "--notes-file",
            str(notes),
            *map(str, sorted(Path("dist").glob("*"))),
        )


if __name__ == "__main__":
    main()
