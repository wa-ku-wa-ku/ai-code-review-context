from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ContextAPIClient:
    """Async HTTP client wrapping the ai-code-review-context API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # -- Index & task listing ------------------------------------------------

    async def index_repo(
        self, repo_id: str, repo_path: str, db_path: str | None = None
    ) -> dict[str, Any]:
        """POST /context/index — build index and return review_tasks."""
        body: dict[str, Any] = {"repo_id": repo_id, "repo_path": repo_path}
        if db_path:
            body["db_path"] = db_path
        resp = await self._client.post("/context/index", json=body)
        resp.raise_for_status()
        return resp.json()

    async def get_tasks(self, repo_id: str) -> list[dict[str, Any]]:
        """GET /demo/{repo_id}/tasks — list tasks (index must be built first)."""
        resp = await self._client.get(f"/demo/{repo_id}/tasks")
        resp.raise_for_status()
        return resp.json().get("review_tasks", [])

    # -- Task package & graph ------------------------------------------------

    async def get_task_package(self, task_id: str, repo_id: str) -> dict[str, Any]:
        """GET /context/task-package/{task_id}"""
        resp = await self._client.get(
            f"/context/task-package/{task_id}", params={"repo_id": repo_id}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_graph_slice(
        self, task_id: str, repo_id: str, depth: int = 2
    ) -> dict[str, Any]:
        """GET /context/tasks/{task_id}/graph-slice"""
        resp = await self._client.get(
            f"/context/tasks/{task_id}/graph-slice",
            params={"repo_id": repo_id, "depth": depth},
        )
        resp.raise_for_status()
        return resp.json()

    # -- Node & file detail --------------------------------------------------

    async def get_node_detail(
        self,
        repo_id: str,
        *,
        symbol_name: str | None = None,
        node_id: str | None = None,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, Any] | None:
        """GET /context/node-detail — returns None on 404."""
        params: dict[str, Any] = {"repo_id": repo_id}
        if symbol_name:
            params["symbol_name"] = symbol_name
        if node_id:
            params["node_id"] = node_id
        if task_id:
            params["task_id"] = task_id
        if review_dimension:
            params["review_dimension"] = review_dimension
        resp = await self._client.get("/context/node-detail", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def get_file_snippet(
        self,
        repo_id: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        *,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, Any]:
        """GET /context/file-snippet"""
        params: dict[str, Any] = {"repo_id": repo_id, "file_path": file_path}
        if start_line is not None:
            params["start_line"] = start_line
        if end_line is not None:
            params["end_line"] = end_line
        if task_id:
            params["task_id"] = task_id
        if review_dimension:
            params["review_dimension"] = review_dimension
        resp = await self._client.get("/context/file-snippet", params=params)
        resp.raise_for_status()
        return resp.json()

    # -- Graph traversal -----------------------------------------------------

    async def get_callees(
        self,
        repo_id: str,
        *,
        symbol_name: str | None = None,
        node_id: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /context/callees"""
        params: dict[str, Any] = {"repo_id": repo_id, "depth": depth}
        if symbol_name:
            params["symbol_name"] = symbol_name
        if node_id:
            params["node_id"] = node_id
        if task_id:
            params["task_id"] = task_id
        if review_dimension:
            params["review_dimension"] = review_dimension
        resp = await self._client.get("/context/callees", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_callers(
        self,
        repo_id: str,
        *,
        symbol_name: str | None = None,
        node_id: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /context/callers"""
        params: dict[str, Any] = {"repo_id": repo_id, "depth": depth}
        if symbol_name:
            params["symbol_name"] = symbol_name
        if node_id:
            params["node_id"] = node_id
        if task_id:
            params["task_id"] = task_id
        if review_dimension:
            params["review_dimension"] = review_dimension
        resp = await self._client.get("/context/callers", params=params)
        resp.raise_for_status()
        return resp.json()

    # -- Related context -----------------------------------------------------

    async def get_related_context(
        self,
        repo_id: str,
        task_id: str,
        *,
        target_file: str | None = None,
        review_dimension: str = "function_logic",
        tags: list[str] | None = None,
        max_depth: int = 2,
        max_files: int = 5,
    ) -> dict[str, Any]:
        """POST /context/related-context"""
        body: dict[str, Any] = {
            "repo_id": repo_id,
            "task_id": task_id,
            "review_dimension": review_dimension,
            "max_depth": max_depth,
            "max_files": max_files,
        }
        if target_file:
            body["target_file"] = target_file
        if tags:
            body["tags"] = tags
        resp = await self._client.post("/context/related-context", json=body)
        resp.raise_for_status()
        return resp.json()

    # -- Feedback ------------------------------------------------------------

    async def submit_feedback(
        self,
        repo_id: str,
        task_id: str,
        *,
        agent: str,
        status: str,
        context_sufficient: bool,
        feedback_type: str,
        message: str | None = None,
        need_more_context: bool = False,
        requested_context: list[dict[str, Any]] | None = None,
        downstream_result_ref: str | None = None,
    ) -> dict[str, Any]:
        """POST /context/task-feedback"""
        body: dict[str, Any] = {
            "repo_id": repo_id,
            "task_id": task_id,
            "agent": agent,
            "status": status,
            "context_sufficient": context_sufficient,
            "feedback_type": feedback_type,
            "need_more_context": need_more_context,
        }
        if message:
            body["message"] = message
        if requested_context:
            body["requested_context"] = requested_context
        if downstream_result_ref:
            body["downstream_result_ref"] = downstream_result_ref
        resp = await self._client.post("/context/task-feedback", json=body)
        resp.raise_for_status()
        return resp.json()
