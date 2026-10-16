"""Durable source mapping resolution. Names never establish identity."""
from .data_contracts import ENTITY_TARGETS


class UnresolvedIdentity(ValueError):
    pass


def resolve_identity(source, entity_type, source_id, lookup):
    if entity_type not in ENTITY_TARGETS or not isinstance(source_id, str) or not source_id.strip():
        raise UnresolvedIdentity("Invalid source identity")
    mapping = lookup("source_mappings", (source, entity_type, source_id))
    if mapping is None:
        raise UnresolvedIdentity(f"Unmapped {source} {entity_type} ID {source_id}")
    if lookup(ENTITY_TARGETS[entity_type], (mapping.canonical_id,)) is None:
        raise UnresolvedIdentity("Source mapping has no canonical record")
    return mapping.canonical_id
