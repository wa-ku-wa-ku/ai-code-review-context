from typing import Any

from repo_context.service.context_service import ContextService


def get_related_context(
    service: ContextService,
    node_id: str,
    include_source: bool = False,
) -> dict[str, Any]:
    return service.get_related_context(
        node_id=node_id,
        include_source=include_source,
    )
