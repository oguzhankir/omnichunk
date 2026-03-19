from __future__ import annotations

from dataclasses import dataclass, field

from omnichunk.types import ByteRange, EntityInfo, EntityType


@dataclass
class ScopeNode:
    entity: EntityInfo
    children: list[ScopeNode] = field(default_factory=list)
    parent: ScopeNode | None = None


@dataclass
class ScopeTree:
    root: list[ScopeNode] = field(default_factory=list)
    imports: list[EntityInfo] = field(default_factory=list)
    exports: list[EntityInfo] = field(default_factory=list)
    all_entities: list[EntityInfo] = field(default_factory=list)


def build_scope_tree(entities: list[EntityInfo]) -> ScopeTree:
    imports = [e for e in entities if e.type == EntityType.IMPORT]
    exports = [e for e in entities if e.type == EntityType.EXPORT]
    scoped = [
        e
        for e in entities
        if e.byte_range is not None and e.type not in {EntityType.IMPORT, EntityType.EXPORT}
    ]
    scoped.sort(
        key=lambda e: (
            e.byte_range.start if e.byte_range else 0,
            -(e.byte_range.end if e.byte_range else 0),
        )
    )

    roots: list[ScopeNode] = []

    for entity in scoped:
        entity_range = entity.byte_range
        if entity_range is None:
            continue
        candidate_parent: ScopeNode | None = None
        for root in roots:
            candidate_parent = _find_deepest_container(root, entity_range)
            if candidate_parent is not None:
                break

        node = ScopeNode(entity=entity)
        if candidate_parent is None:
            roots.append(node)
        else:
            node.parent = candidate_parent
            candidate_parent.children.append(node)

    return ScopeTree(root=roots, imports=imports, exports=exports, all_entities=list(entities))


def find_scope_chain(scope_tree: ScopeTree, byte_range: ByteRange) -> list[EntityInfo]:
    chain: list[EntityInfo] = []

    current_level: list[ScopeNode] = scope_tree.root
    while current_level:
        found = False
        for node in current_level:
            node_range = node.entity.byte_range
            if node_range is None:
                continue
            if not _contains(node_range, byte_range):
                continue
            chain.append(node.entity)
            current_level = node.children
            found = True
            break
        if not found:
            break

    return list(reversed(chain))


def _find_deepest_container(node: ScopeNode, target: ByteRange) -> ScopeNode | None:
    current_range = node.entity.byte_range
    if current_range is None or not _contains(current_range, target):
        return None

    result = node
    children = node.children
    while children:
        found = False
        for child in children:
            child_range = child.entity.byte_range
            if child_range is not None and _contains(child_range, target):
                result = child
                children = child.children
                found = True
                break
        if not found:
            break

    return result


def _contains(outer: ByteRange, inner: ByteRange) -> bool:
    return outer.start <= inner.start and outer.end >= inner.end
