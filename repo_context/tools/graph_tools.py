from typing import Any

from repo_context.service.context_service import ContextService


def get_callees(
    service: ContextService,
    node_id: str,
    depth: int = 1,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return service.get_callees(node_id=node_id, depth=depth, limit=limit)


def get_callers(
    service: ContextService,
    node_id: str,
    depth: int = 1,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return service.get_callers(node_id=node_id, depth=depth, limit=limit)


def trace_call_chain(
    service: ContextService,
    source_node_id: str,
    target_node_id: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    return service.trace_call_chain(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        max_depth=max_depth,
    )


def explore_related_symbols(
    service: ContextService,
    node_id: str,
    include_source: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    return service.explore_related_symbols(
        node_id=node_id,
        include_source=include_source,
        limit=limit,
    )
