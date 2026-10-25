"""Native LlamaIndex parser/ingestion transform. Install ``omnichunk[llamaindex]``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
from typing import Any, cast

from llama_index.core.bridge.pydantic import Field
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import NodeParser
from llama_index.core.schema import (
    BaseNode,
    Document,
    MetadataMode,
    NodeRelationship,
    RelatedNodeInfo,
    TextNode,
)

from ._common import split_source

_INGESTION_IDENTITY = "_omnichunk_ingestion_identity"


class OmniChunkNodeParser(NodeParser):
    """Cacheable native parser with exact citations and optional hierarchy.

    Options must be JSON serializable for ingestion cache identity. Use named
    tokenizers rather than callbacks. Metadata remains available to filtering but
    is excluded from model rendering; embedding input is exactly the selected
    raw/contextualized payload. Metadata storage does not enforce authorization.
    """

    options: dict[str, Any] = Field(default_factory=dict)
    filepath: str = "document.txt"
    use_contextualized_text: bool = False
    levels: list[int] | None = None
    adapter_revision: str = "omnichunk-native-v1"

    def __init__(self, **data: Any) -> None:
        if "id_func" in data:
            raise ValueError("OmniChunk manages stable node IDs; id_func is not supported")
        options = data.get("options", {})
        try:
            json.dumps(options, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Parser options must be JSON serializable for ingestion caching"
            ) from exc
        super().__init__(**data)

    @classmethod
    def class_name(cls) -> str:
        return "OmniChunkNodeParser"

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        # Configuration can be mutated through Pydantic fields after construction.
        # Revalidate before constructing the ingestion cache's transform key.
        try:
            json.dumps(self.options, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Parser options must be JSON serializable for ingestion caching"
            ) from exc
        data = super().to_dict(**kwargs)
        # IDs are produced from source/chunk identity, not NodeParser.id_func.
        # Its default callable does not round-trip across LlamaIndex versions.
        data.pop("id_func", None)
        return data

    def _parse_nodes(
        self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any
    ) -> list[BaseNode]:
        result: list[BaseNode] = []
        for source in nodes:
            identity = source.metadata.get(_INGESTION_IDENTITY)
            if _INGESTION_IDENTITY in source.metadata and (
                not isinstance(identity, dict)
                or set(identity) != {"fingerprint", "source_hash"}
                or not all(isinstance(value, str) for value in identity.values())
            ):
                raise ValueError(f"Reserved ingestion metadata key: {_INGESTION_IDENTITY}")
            source_metadata = {
                key: value for key, value in source.metadata.items() if key != _INGESTION_IDENTITY
            }
            items = split_source(
                source.get_content(metadata_mode=MetadataMode.NONE),
                source_metadata,
                source.node_id,
                options=self.options,
                filepath=self.filepath,
                levels=self.levels,
            )
            groups: dict[int, list[TextNode]] = {}
            for item in items:
                payload = (
                    item.chunk.contextualized_text
                    if self.use_contextualized_text
                    else item.chunk.text
                )
                # SOURCE points to the original framework document. Logical
                # OmniChunk source_id may be independently caller-selected.
                source_info = deepcopy(source.as_related_node_info())
                source_info.metadata.pop(_INGESTION_IDENTITY, None)
                if isinstance(identity, dict):
                    source_info.hash = identity["source_hash"]
                relationships: dict[NodeRelationship, RelatedNodeInfo | list[RelatedNodeInfo]] = {
                    NodeRelationship.SOURCE: source_info
                }
                if item.parent_id is not None:
                    relationships[NodeRelationship.PARENT] = RelatedNodeInfo(node_id=item.parent_id)
                if item.children:
                    relationships[NodeRelationship.CHILD] = [
                        RelatedNodeInfo(node_id=x) for x in item.children
                    ]
                metadata = (
                    item.metadata
                    if self.include_metadata
                    else {"omnichunk": item.metadata["omnichunk"]}
                )
                node = TextNode(
                    id_=item.node_id,
                    text=payload,
                    metadata=metadata,
                    relationships=relationships,
                    start_char_idx=item.char_start,
                    end_char_idx=item.char_end,
                    excluded_embed_metadata_keys=list(metadata),
                    excluded_llm_metadata_keys=list(metadata),
                )
                groups.setdefault(item.level, []).append(node)
                result.append(node)
            if self.include_prev_next_rel:
                for group in groups.values():
                    for i, node in enumerate(group):
                        if i:
                            node.relationships[NodeRelationship.PREVIOUS] = RelatedNodeInfo(
                                node_id=group[i - 1].node_id
                            )
                        if i + 1 < len(group):
                            node.relationships[NodeRelationship.NEXT] = RelatedNodeInfo(
                                node_id=group[i + 1].node_id
                            )
        return result

    def _postprocess_parsed_nodes(
        self, nodes: list[BaseNode], parent_doc_map: dict[str, Document]
    ) -> list[BaseNode]:
        # The base implementation searches rendered text in the source and adds
        # cross-level adjacency. Exact source indices/relationships are set above.
        return nodes


class OmniChunkIngestionPipeline(IngestionPipeline):
    """Native pipeline whose cache distinguishes identical text from different sources.

    LlamaIndex's ordinary cache key excludes document IDs and can return another
    document's cached citations. This pipeline copies inputs and fingerprints
    their complete JSON source records before cache lookup. Its first transform
    must be :class:`OmniChunkNodeParser`; subsequent transforms remain caller-owned.
    Internal identity metadata is removed by the parser and never embedded.
    """

    def __init__(self, **data: Any) -> None:
        if "transformations" not in data:
            data["transformations"] = [OmniChunkNodeParser()]
        super().__init__(**data)
        if not self.transformations or not isinstance(self.transformations[0], OmniChunkNodeParser):
            raise ValueError("OmniChunkIngestionPipeline requires OmniChunkNodeParser first")

    def _prepare_inputs(
        self, documents: Sequence[Document] | None, nodes: Sequence[BaseNode] | None
    ) -> list[BaseNode]:
        # Both run() and arun() call this before deduplication and cache lookup.
        if not self.transformations or not isinstance(self.transformations[0], OmniChunkNodeParser):
            raise ValueError("OmniChunkIngestionPipeline requires OmniChunkNodeParser first")
        result = []
        for source in super()._prepare_inputs(documents, nodes):
            if _INGESTION_IDENTITY in source.metadata:
                raise ValueError(f"Reserved ingestion metadata key: {_INGESTION_IDENTITY}")
            try:
                raw = json.dumps(
                    {"node": source.to_dict(), "native_hash": source.hash},
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("Ingestion source records must be finite JSON values") from exc
            copied = deepcopy(source)
            fingerprint = sha256(raw.encode("utf-8")).hexdigest()
            copied.metadata[_INGESTION_IDENTITY] = {
                "fingerprint": fingerprint,
                "source_hash": source.hash,
            }
            # A source may hide metadata with a custom text/metadata template.
            # Normalize only the private copy; raw source text remains unchanged.
            copied.metadata_template = "{key}: {value}"
            if hasattr(copied, "metadata_separator"):
                copied.metadata_separator = "\n"
            else:
                # The declared minimum LlamaIndex version uses this spelling.
                cast(Any, copied).metadata_seperator = "\n"
            if hasattr(copied, "text_template"):
                copied.text_template = "{metadata_str}\n\n{content}"
            if fingerprint not in copied.get_content(MetadataMode.ALL):
                raise ValueError("Ingestion source must expose identity metadata to the cache")
            result.append(copied)
        return result
