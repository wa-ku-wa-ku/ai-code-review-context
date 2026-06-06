"""上下文处理模块 API 调用封装。"""

from pathlib import Path
from typing import Any

import httpx


class ContextApiClient:
    """下游 agent 访问 repo_context FastAPI 服务的最小 client。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ContextApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def build_index(
        self,
        *,
        repo_id: str,
        repo_path: str | Path,
        db_path: str | Path | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repo_id": repo_id,
            "repo_path": str(repo_path),
        }
        if db_path is not None:
            payload["db_path"] = str(db_path)
        return self._request("POST", "/context/index", json=payload)

    def get_task_package(self, *, repo_id: str, task_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/context/task-package/{task_id}",
            params={"repo_id": repo_id},
        )

    def list_tasks(
        self,
        *,
        repo_id: str,
        review_dimension: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/context/tasks",
            params={"repo_id": repo_id, "review_dimension": review_dimension},
        )

    def get_task_graph_slice(
        self,
        *,
        repo_id: str,
        task_id: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/context/tasks/{task_id}/graph-slice",
            params={"repo_id": repo_id, "depth": depth},
        )

    def get_related_context(
        self,
        *,
        repo_id: str,
        task_id: str,
        target_file: str | None,
        review_dimension: str | None,
        tags: list[str] | None = None,
        max_depth: int = 1,
        max_files: int = 3,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/context/related-context",
            json={
                "repo_id": repo_id,
                "task_id": task_id,
                "target_file": target_file,
                "review_dimension": review_dimension,
                "tags": tags or [],
                "max_depth": max_depth,
                "max_files": max_files,
            },
        )

    def get_file_snippet(
        self,
        *,
        repo_id: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/context/file-snippet",
            params={
                "repo_id": repo_id,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "task_id": task_id,
                "review_dimension": review_dimension,
            },
        )

    def get_node_detail(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/context/node-detail",
            params={
                "repo_id": repo_id,
                "node_id": node_id,
                "symbol_name": symbol_name,
                "task_id": task_id,
                "review_dimension": review_dimension,
            },
        )

    def get_callees(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/context/callees",
            params={
                "repo_id": repo_id,
                "node_id": node_id,
                "symbol_name": symbol_name,
                "depth": depth,
                "task_id": task_id,
                "review_dimension": review_dimension,
            },
        )

    def get_callers(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/context/callers",
            params={
                "repo_id": repo_id,
                "node_id": node_id,
                "symbol_name": symbol_name,
                "depth": depth,
                "task_id": task_id,
                "review_dimension": review_dimension,
            },
        )

    def submit_task_feedback(
        self,
        *,
        repo_id: str,
        task_id: str,
        agent: str,
        status: str,
        context_sufficient: bool,
        feedback_type: str,
        message: str | None = None,
        need_more_context: bool = False,
        requested_context: list[dict[str, Any]] | None = None,
        downstream_result_ref: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/context/task-feedback",
            json={
                "repo_id": repo_id,
                "task_id": task_id,
                "agent": agent,
                "status": status,
                "context_sufficient": context_sufficient,
                "feedback_type": feedback_type,
                "message": message,
                "need_more_context": need_more_context,
                "requested_context": requested_context or [],
                "downstream_result_ref": downstream_result_ref,
            },
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        response = self._client.request(method, url, **_drop_none_values(kwargs))
        response.raise_for_status()
        return response.json()


def _drop_none_values(kwargs: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(kwargs)
    for key in ("params", "json"):
        value = cleaned.get(key)
        if isinstance(value, dict):
            cleaned[key] = {
                item_key: item_value
                for item_key, item_value in value.items()
                if item_value is not None
            }
    return cleaned
