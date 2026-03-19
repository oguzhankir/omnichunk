from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "rust" / "omnichunk_rust" / "Cargo.toml"
DEFAULT_OUT_DIR = ROOT / "dist-rust"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build omnichunk Rust extension wheel via maturin.",
    )
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST),
        help="Path to Cargo.toml for the Rust extension",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Output directory for built wheels",
    )
    parser.add_argument("--release", action="store_true", help="Build with --release")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Build wheel only, skip pip install",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    manifest_path = Path(args.manifest_path)
    if not manifest_path.exists():
        print(f"Manifest path does not exist: {manifest_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    build_cmd = [
        sys.executable,
        "-m",
        "maturin",
        "build",
        "--manifest-path",
        str(manifest_path),
        "--out",
        str(out_dir),
    ]
    if args.release:
        build_cmd.append("--release")

    build_proc = subprocess.run(build_cmd, cwd=str(ROOT), check=False)
    if build_proc.returncode != 0:
        return int(build_proc.returncode)

    wheels = sorted(out_dir.glob("omnichunk_rust-*.whl"))
    if not wheels:
        print("No wheel file was produced by maturin build.", file=sys.stderr)
        return 1

    wheel_path = wheels[-1]
    print(f"Built wheel: {wheel_path}")

    if args.skip_install:
        return 0

    install_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        str(wheel_path),
    ]
    install_proc = subprocess.run(install_cmd, cwd=str(ROOT), check=False)
    return int(install_proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
