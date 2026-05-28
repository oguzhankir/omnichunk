from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.formats.tex import load_latex


def _chunks(src: str) -> list:
    return Chunker(max_chunk_size=200, min_chunk_size=20, size_unit="chars").chunk(
        "doc.tex", src
    )


def _math_balanced(text: str, env: str) -> bool:
    return text.count(f"\\begin{{{env}}}") == text.count(f"\\end{{{env}}}")


def test_latex_math_reconstruction(fixtures_dir: Path) -> None:
    src = (fixtures_dir / "sample_math.tex").read_text(encoding="utf-8")
    chunks = _chunks(src)
    assert "".join(c.text for c in chunks) == src


def test_latex_equation_block_atomic(fixtures_dir: Path) -> None:
    src = (fixtures_dir / "sample_math.tex").read_text(encoding="utf-8")
    chunks = _chunks(src)
    for ch in chunks:
        assert _math_balanced(ch.text, "equation"), (
            f"equation env split across chunk boundary: {ch.text[:60]!r}"
        )


def test_latex_align_block_atomic(fixtures_dir: Path) -> None:
    src = (fixtures_dir / "sample_math.tex").read_text(encoding="utf-8")
    chunks = _chunks(src)
    for ch in chunks:
        assert _math_balanced(ch.text, "align"), (
            f"align env split: {ch.text[:60]!r}"
        )


def test_latex_display_bracket_math_kept_together() -> None:
    src = "Intro \\[ a + b \\] outro.\n"
    chunks = _chunks(src)
    target = next(c for c in chunks if "\\[" in c.text)
    assert "\\]" in target.text


def test_latex_inline_math_dollars_atomic() -> None:
    src = "Some prose. $a^2 + b^2 = c^2$ more prose.\n"
    chunks = _chunks(src)
    target = next(c for c in chunks if "$a^2" in c.text)
    assert "$a^2 + b^2 = c^2$" in target.text


def test_latex_lstlisting_language_metadata() -> None:
    src = "\\begin{lstlisting}[language=Python]\ndef f(): return 1\n\\end{lstlisting}\n"
    doc = load_latex(src)
    code_segs = [s for s in doc.segments if s.kind == "code"]
    assert code_segs
    assert code_segs[0].metadata.get("latex_language") == "python"


def test_latex_footnote_does_not_force_split() -> None:
    src = "Body text\\footnote{This is a side note.} more body.\n"
    chunks = _chunks(src)
    # Reconstruction must hold; footnote is just inline text.
    assert "".join(c.text for c in chunks) == src
    assert any("\\footnote" in c.text and "side note" in c.text for c in chunks)


def test_latex_bibliography_commands_preserved() -> None:
    src = (
        "Intro\n\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\n"
        "More text.\n"
    )
    chunks = _chunks(src)
    full = "".join(c.text for c in chunks)
    assert "\\bibliographystyle{plain}" in full
    assert "\\bibliography{refs}" in full


def test_latex_label_inside_equation_preserved() -> None:
    src = "\\begin{equation}\nE = mc^2 \\label{eq:main}\n\\end{equation}\n"
    chunks = _chunks(src)
    target = next(c for c in chunks if "\\begin{equation}" in c.text)
    assert "\\label{eq:main}" in target.text


def test_latex_load_segments_have_math_metadata(fixtures_dir: Path) -> None:
    src = (fixtures_dir / "sample_math.tex").read_text(encoding="utf-8")
    doc = load_latex(src)
    math_metas = {
        s.metadata.get("latex_math") for s in doc.segments if "latex_math" in s.metadata
    }
    assert "equation" in math_metas
    assert "align" in math_metas
    assert "display_bracket" in math_metas
