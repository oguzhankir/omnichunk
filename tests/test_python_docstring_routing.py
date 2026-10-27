"""Only real Python docstrings contribute to documentation-heavy routing."""

from __future__ import annotations

import pytest

from omnichunk import Chunker, ContentType
from omnichunk.util.detect import _looks_hybrid_python, detect_content_type


@pytest.mark.parametrize(
    "statement",
    [
        'SQL = """SELECT id, account FROM transactions WHERE approved = TRUE;"""',
        (
            'def query():\n    return """SELECT id, account FROM transactions '
            'WHERE approved = TRUE;"""'
        ),
        (
            'def query():\n    payload = """SELECT id, account FROM transactions '
            'WHERE approved = TRUE;"""\n    return payload'
        ),
        (
            'def query():\n    pass\n    """This later string expression is not a docstring, '
            'even when it dominates the file."""'
        ),
        'value = f"""A formatted string with {1 + 2} is data, not a docstring."""',
        'f"""A formatted string with {1 + 2} is not a Python docstring."""',
        'b"""A byte string is not a Python documentation string."""',
    ],
)
def test_data_strings_and_later_expressions_stay_code(statement):
    assert not _looks_hybrid_python(statement)
    assert detect_content_type("query.py", statement) == ContentType.CODE


@pytest.mark.parametrize(
    "declaration", ["module", "class Entry:", "def entry():", "async def entry():"]
)
@pytest.mark.parametrize("prefix", ["", "r", "u"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_real_unicode_raw_docstrings_remain_hybrid(declaration, prefix, newline):
    literal = prefix + "'''İşlemi güvenle kaydedin. 確認してから保存する。 😀'''"
    source = (
        literal + "\nvalue = 1\n"
        if declaration == "module"
        else declaration + "\n    " + literal + "\n    pass\n"
    )
    source = source.replace("\n", newline)
    assert _looks_hybrid_python(source)
    assert detect_content_type("entry.py", source) == ContentType.HYBRID


@pytest.mark.parametrize(
    "source",
    [
        'def broken(:\n    """This large docstring-looking text is not valid Python."""',
        '"""An unterminated literal remains code, including all of this explanation.',
        '"""A valid literal followed by invalid syntax should not route as prose."""\nif:',
        '"""A valid literal followed by a null byte should remain code."""\x00',
    ],
)
def test_malformed_python_uses_conservative_code_route(source):
    assert not _looks_hybrid_python(source)
    assert detect_content_type("broken.py", source) == ContentType.CODE


def test_unicode_byte_lengths_match_exact_source_literal_not_decoded_value():
    # The ASCII data literal dominates characters, but the real docstring
    # dominates UTF-8 source bytes. AST byte columns must use the same unit.
    source = 'def görev():\n    """' + ("😀" * 20) + '"""\n    return "' + ("x" * 70) + '"\n'
    assert _looks_hybrid_python(source)
    escaped = '"""' + ("\\u0061" * 40) + '"""\nvalue = "' + ("x" * 100) + '"\n'
    assert _looks_hybrid_python(escaped)


def test_detection_does_not_execute_python():
    source = '"""' + ("Documentation. " * 20) + '"""\nraise RuntimeError("must not execute")\n'
    assert detect_content_type("safe.py", source) == ContentType.HYBRID


def test_sql_data_routes_through_code_engine_with_exact_citations():
    source = (
        'def report():\n    return """SELECT id, amount FROM invoices WHERE approved = TRUE;"""\n'
    )
    chunks = Chunker(
        max_chunk_size=40, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    ).chunk("report.py", source)
    assert "".join(c.text for c in chunks) == source
    assert all(c.context.content_type == ContentType.CODE for c in chunks)
    for c in chunks:
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert len(c.contextualized_text) <= 40


def test_unicode_line_separators_inside_docstrings_do_not_shift_ast_lines():
    source = 'value = "before"\nclass Entry:\n    """' + ("İ😀\u2028" * 20) + '"""\n    pass\n'
    assert _looks_hybrid_python(source)
