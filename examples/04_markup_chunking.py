"""
Markup-style formats: JSON, YAML, TOML, HTML — breadcrumbs show logical path.
"""

from __future__ import annotations

from omnichunk import Chunker


def main() -> None:
    chunker = Chunker(max_chunk_size=256, size_unit="chars", min_chunk_size=20)

    json_src = '{"users": [{"id": 1, "name": "Ada"}], "meta": {"v": 2}}'
    yaml_src = """
app:
  name: demo
  port: 8080
"""
    toml_src = """
[server]
host = "127.0.0.1"
port = 9000
"""
    html_src = "<html><body><div id='main'><p>Hi</p></div></body></html>"

    for label, fp, src in [
        ("JSON", "data.json", json_src),
        ("YAML", "cfg.yaml", yaml_src),
        ("TOML", "cfg.toml", toml_src),
        ("HTML", "page.html", html_src),
    ]:
        chunks = chunker.chunk(fp, src)
        print(f"{label}: language={chunks[0].context.language if chunks else '?'} chunks={len(chunks)}")
        for c in chunks:
            print(f"  breadcrumb: {' > '.join(c.context.breadcrumb) or '(root)'}")


if __name__ == "__main__":
    main()
