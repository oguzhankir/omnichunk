from __future__ import annotations

from omnichunk import Chunker
from omnichunk.parser.html_parser import parse_html_structure


def test_template_element_recognised() -> None:
    src = "<template id='tmpl'><p>x</p></template>"
    nodes = parse_html_structure(src)
    template = next(n for n in nodes if n.tag == "template")
    assert template is not None
    assert template.metadata == {}  # no surfaced attrs aside from id (not whitelisted)
    # Inner <p> must be a separate node so the template body is logically isolated.
    assert any(n.tag == "p" for n in nodes)


def test_custom_element_flagged_as_custom() -> None:
    src = "<my-widget data-id='42'>hello</my-widget>"
    nodes = parse_html_structure(src)
    widget = next(n for n in nodes if n.tag == "my-widget")
    assert widget.is_custom_element is True
    assert widget.metadata.get("data-id") == "42"


def test_plain_div_not_marked_custom() -> None:
    src = "<div>hello</div>"
    nodes = parse_html_structure(src)
    div = next(n for n in nodes if n.tag == "div")
    assert div.is_custom_element is False


def test_script_module_type_metadata() -> None:
    src = '<script type="module">import x from "./x.js";</script>'
    nodes = parse_html_structure(src)
    script = next(n for n in nodes if n.tag == "script")
    assert script.metadata.get("type") == "module"


def test_script_importmap_type_metadata() -> None:
    src = '<script type="importmap">{"imports":{}}</script>'
    nodes = parse_html_structure(src)
    script = next(n for n in nodes if n.tag == "script")
    assert script.metadata.get("type") == "importmap"


def test_style_block_does_not_crash_parser() -> None:
    src = "<style>.foo { color: red; } @media (min-width: 0) { .x{ } }</style>"
    nodes = parse_html_structure(src)
    assert any(n.tag == "style" for n in nodes)


def test_aria_label_surfaced_in_metadata() -> None:
    src = '<button aria-label="close dialog">x</button>'
    nodes = parse_html_structure(src)
    btn = next(n for n in nodes if n.tag == "button")
    assert btn.metadata.get("aria-label") == "close dialog"


def test_data_attribute_surfaced_in_metadata() -> None:
    src = '<section data-section="main" data-rank="1">body</section>'
    nodes = parse_html_structure(src)
    sec = next(n for n in nodes if n.tag == "section")
    assert sec.metadata.get("data-section") == "main"
    assert sec.metadata.get("data-rank") == "1"


def test_chunker_reconstruction_with_modern_html() -> None:
    src = (
        "<!DOCTYPE html>\n<html>\n<body>\n"
        '<template id="t"><p>X</p></template>\n'
        '<my-widget data-id="42">hi</my-widget>\n'
        '<script type="module">import a from "./a.js"</script>\n'
        "</body></html>\n"
    )
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "page.html", src
    )
    assert chunks
    assert "".join(c.text for c in chunks) == src


def test_existing_markup_chunking_still_works() -> None:
    """Smoke test that plain HTML chunking didn't regress."""
    src = "<html><head><title>X</title></head><body><p>Hello world</p></body></html>"
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "page.html", src
    )
    assert "".join(c.text for c in chunks) == src
