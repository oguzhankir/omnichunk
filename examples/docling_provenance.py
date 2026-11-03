"""Already-extracted Docling text -> chunks -> JSON/frameworks -> original references.

Run after ``pip install -e '.[docling,langchain,llamaindex]'``. This constructs an
authored extraction fixture with the real schema; it does not read/convert a PDF,
run OCR, download models, call a service or write an index.
"""

from __future__ import annotations

import json

from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)
from llama_index.core.schema import MetadataMode

from omnichunk import ChunkOptions, chunk_from_dict, chunk_loaded_document, load_docling_document
from omnichunk.serialization import (
    chunks_to_jsonl,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
)


def main() -> None:
    # In an application this is an already-extracted DoclingDocument or its
    # exported dictionary. Keep it alongside the canonical text to resolve IDs.
    extracted = DoclingDocument(name="Authored multilingual guide")
    for page in (1, 2):
        extracted.add_page(page_no=page, size=Size(width=600, height=800))
    extracted.add_heading("Kılavuz", level=1)
    for page, text in [(1, "Türkçe e\u0301 👩‍💻."), (2, "第二页保留来源。")]:
        extracted.add_text(
            label=DocItemLabel.PARAGRAPH,
            text=text,
            prov=ProvenanceItem(
                page_no=page, bbox=BoundingBox(l=10, t=20, r=500, b=60), charspan=(0, len(text))
            ),
        )
    values = [
        ["Ad", "Değer"],
        ["İlk", "你好 source value"],
        ["İkinci", "42 canonical"],
        ["Son", ""],
    ]
    extracted.add_table(
        data=TableData(
            num_rows=4,
            num_cols=2,
            table_cells=[
                TableCell(
                    text=text,
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    column_header=row == 0,
                )
                for row, cells in enumerate(values)
                for col, text in enumerate(cells)
            ],
        )
    )
    loaded = load_docling_document(
        extracted, source_id="manual:example", extraction_revision="authored:v1"
    )
    chunks = chunk_loaded_document(
        "guide.pdf",
        loaded,
        ChunkOptions(max_chunk_size=80, min_chunk_size=0, coverage_policy="lossless"),
    )
    assert "".join(chunk.text for chunk in chunks) == loaded.text
    assert any("# Table headers (derived)" in chunk.contextualized_text for chunk in chunks)
    restored = [chunk_from_dict(json.loads(line)) for line in chunks_to_jsonl(chunks).splitlines()]
    assert restored == chunks
    langchain = chunks_to_langchain_docs(restored)
    llamaindex = chunks_to_llamaindex_docs(restored, include_metadata_in_content=False)
    exported = extracted.model_dump(mode="json")
    for original, lc, li in zip(chunks, langchain, llamaindex):
        assert lc.page_content == li.get_content(MetadataMode.EMBED) == original.contextualized_text
        assert len(lc.page_content) <= 80
        for document in (lc, li):
            recovered = chunk_from_dict(document.metadata["omnichunk"])
            assert recovered == original
            assert recovered.source.source_id == "manual:example"
            span = recovered.byte_range
            assert loaded.text.encode()[span.start : span.end].decode() == recovered.text
            for reference in recovered.context.format_metadata["elements"]:
                collection, offset = reference["element_id"][2:].split("/")
                element = exported[collection][int(offset)]
                assert element["self_ref"] == reference["element_id"]
                for prov in reference["metadata"]["provenance"]:
                    assert prov["bbox"] in [item["bbox"] for item in element["prov"]]
                    assert str(prov["page_no"]) in exported["pages"]
        print(
            original.index, [r["element_id"] for r in original.context.format_metadata["elements"]]
        )
    print(f"Resolved {len(chunks)} chunks through JSON, LangChain and LlamaIndex.")


if __name__ == "__main__":
    main()
