from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

_DEFAULT_FIXTURE_FILES: tuple[str, ...] = (
    "python_complex.py",
    "typescript_complex.ts",
    "rust_complex.rs",
    "markdown_doc.md",
    "html_page.html",
    "sample.json",
    "sample.yaml",
    "sample.toml",
    "mixed_notebook.py",
)


@dataclass(frozen=True)
class CorpusEntry:
    filepath: str
    text: str


def collect_corpus_entries(
    *,
    mode: str,
    repeat: int,
    directory: str | None,
    glob_pattern: str,
    max_files: int,
    encoding: str = "utf-8",
) -> list[CorpusEntry]:
    return list(
        iter_corpus_entries(
            mode=mode,
            repeat=repeat,
            directory=directory,
            glob_pattern=glob_pattern,
            max_files=max_files,
            encoding=encoding,
        )
    )


def iter_corpus_entries(
    *,
    mode: str,
    repeat: int,
    directory: str | None,
    glob_pattern: str,
    max_files: int,
    encoding: str = "utf-8",
) -> Iterator[CorpusEntry]:
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    if max_files < 1:
        raise ValueError("max_files must be >= 1")

    if mode == "fixtures":
        templates = _load_fixture_templates(encoding=encoding)
        for rep in range(repeat):
            for name, text in templates:
                yield CorpusEntry(filepath=f"fixtures/{rep:04d}_{name}", text=text)
        return

    if mode == "mega-python":
        base = (FIXTURES / "python_complex.py").read_text(encoding=encoding)
        parts: list[str] = ["# synthetic large python corpus\n\n"]
        for idx in range(repeat):
            parts.append(f"# block {idx}\n")
            parts.append(base)
            parts.append("\n\n")
        yield CorpusEntry(filepath="synthetic/mega_python.py", text="".join(parts))
        return

    if mode == "directory":
        if directory is None:
            raise ValueError("directory mode requires --directory")

        root = Path(directory)
        if not root.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")
        if not root.is_dir():
            raise NotADirectoryError(f"Expected directory but got: {directory}")

        count = 0
        for path in sorted(root.glob(glob_pattern), key=lambda item: item.as_posix()):
            if count >= max_files:
                break
            if not path.is_file():
                continue

            try:
                text = path.read_text(encoding=encoding)
            except (UnicodeDecodeError, OSError):
                continue

            yield CorpusEntry(filepath=str(path), text=text)
            count += 1
        return

    raise ValueError(f"Unsupported corpus mode: {mode}")


def _load_fixture_templates(*, encoding: str) -> list[tuple[str, str]]:
    templates: list[tuple[str, str]] = []
    for name in _DEFAULT_FIXTURE_FILES:
        path = FIXTURES / name
        if not path.exists():
            continue
        templates.append((name, path.read_text(encoding=encoding)))

    if not templates:
        raise FileNotFoundError("No benchmark fixtures were found under tests/fixtures")

    return templates
