from __future__ import annotations

from pathlib import Path
import sys

FILES = [
    "AI_RULES.md",
    ".cursorrules",
    ".windsurfrules",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    contents: dict[str, str] = {}

    missing: list[str] = []
    for rel in FILES:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        contents[rel] = path.read_text(encoding="utf-8")

    if missing:
        print("Missing rule file(s):")
        for rel in missing:
            print(f"- {rel}")
        return 1

    baseline_name = FILES[0]
    baseline = contents[baseline_name]

    mismatched: list[str] = []
    for rel in FILES[1:]:
        if contents[rel] != baseline:
            mismatched.append(rel)

    if mismatched:
        print("Rule files are not synchronized.")
        print(f"Baseline: {baseline_name}")
        print("Mismatched:")
        for rel in mismatched:
            print(f"- {rel}")
        return 1

    print("Rule files are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
