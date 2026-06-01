from typing import Any

from repo_context.service.context_service import ContextService


def search_symbol(
    service: ContextService,
    keyword: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return service.search_symbol(keyword=keyword, limit=limit)


def get_node_detail(
    service: ContextService,
    node_id: str,
    include_source: bool = False,
) -> dict[str, Any] | None:
    return service.get_node_detail(node_id=node_id, include_source=include_source)
