"""Native LangChain splitter. Install ``omnichunk[langchain]``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from ._common import split_source


class OmniChunkTextSplitter(TextSplitter):
    """Split source documents once while preserving IDs, metadata and citations.

    ``options`` are ordinary Chunker options. ``levels`` optionally emits all
    hierarchy levels with links in reserved ``metadata['omnichunk']``. Supply
    document IDs or per-document ``source_id`` metadata for identity across edits.
    Without them, inline text uses a content-hash identity. Raw text is the default;
    contextualized output is explicit and its source ranges still address raw text.
    """

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        filepath: str = "document.txt",
        use_contextualized_text: bool = False,
        levels: list[int] | None = None,
    ) -> None:
        super().__init__(chunk_overlap=0, strip_whitespace=False)
        # Tokenizer/model callbacks remain caller-owned, as with Chunker itself.
        self.options = dict(options or {})
        self.filepath = filepath
        self.use_contextualized_text = use_contextualized_text
        self.levels = list(levels) if levels is not None else None

    def split_text(self, text: str) -> list[str]:
        return [doc.page_content for doc in self.create_documents([text])]

    def create_documents(
        self, texts: list[str], metadatas: list[dict[Any, Any]] | None = None
    ) -> list[Document]:
        if metadatas is not None and len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have equal lengths")
        return self.split_documents(
            Document(page_content=text, metadata=metadatas[i] if metadatas is not None else {})
            for i, text in enumerate(texts)
        )

    def split_documents(self, documents: Iterable[Document]) -> list[Document]:
        result = []
        for document in documents:
            items = split_source(
                document.page_content,
                document.metadata,
                document.id,
                options=self.options,
                filepath=self.filepath,
                levels=self.levels,
            )
            for item in items:
                content = (
                    item.chunk.contextualized_text
                    if self.use_contextualized_text
                    else item.chunk.text
                )
                result.append(
                    Document(id=item.node_id, page_content=content, metadata=item.metadata)
                )
        return result
