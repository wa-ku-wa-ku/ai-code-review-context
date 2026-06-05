from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from func_logic_agent.client.context_api_client import ContextAPIClient


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock handler that returns sample responses for known endpoints."""
    path = request.url.path

    if path == "/context/index" and request.method == "POST":
        return httpx.Response(200, json={
            "index_result": {"files": 5, "nodes": 10, "edges": 8},
            "repo_summary": {"framework": "fastapi", "python_files": 5},
            "review_tasks": [
                {
                    "task_id": "task_1",
                    "task_type": "entrypoint_review",
                    "review_dimension": "function_logic",
                    "priority": "high",
                    "target": {"file_path": "app/api/auth.py", "symbols": ["login"]},
                }
            ],
        })

    if path.startswith("/demo/") and path.endswith("/tasks") and request.method == "GET":
        return httpx.Response(200, json={
            "review_tasks": [
                {"task_id": "task_1", "task_type": "entrypoint_review"}
            ]
        })

    if path.startswith("/context/task-package/") and request.method == "GET":
        task_id = path.split("/")[-1]
        return httpx.Response(200, json={
            "task_id": task_id,
            "task_type": "entrypoint_review",
            "target": {"file_path": "app/api/auth.py"},
            "context_policy": {"max_graph_depth": 2},
        })

    if "/graph-slice" in path and request.method == "GET":
        return httpx.Response(200, json={
            "task_id": "task_1",
            "nodes": [{"node_id": "n1", "name": "login"}],
            "edges": [],
            "boundary_nodes": [],
        })

    if path == "/context/node-detail" and request.method == "GET":
        return httpx.Response(200, json={
            "node_id": "n1", "name": "login", "source": "def login(): pass"
        })

    if path == "/context/file-snippet" and request.method == "GET":
        return httpx.Response(200, json={
            "file_path": "app/api/auth.py", "content": "def login(): pass"
        })

    if path == "/context/callees" and request.method == "GET":
        return httpx.Response(200, json=[
            {"name": "authenticate", "depth": 1}
        ])

    if path == "/context/callers" and request.method == "GET":
        return httpx.Response(200, json=[
            {"name": "main", "depth": 1}
        ])

    if path == "/context/related-context" and request.method == "POST":
        return httpx.Response(200, json={
            "task_id": "task_1",
            "related_files": ["app/services/user_service.py"],
            "related_symbols": ["authenticate"],
        })

    if path == "/context/task-feedback" and request.method == "POST":
        body = json.loads(request.content)
        return httpx.Response(200, json={
            "accepted": True,
            "feedback_id": "feedback_000001",
            "task_id": body.get("task_id"),
            "status": body.get("status"),
            "next_action": "continue_downstream",
        })

    return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def client():
    transport = httpx.MockTransport(_mock_handler)
    c = ContextAPIClient(base_url="http://testserver", timeout=5.0)
    c._client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return c


@pytest.mark.asyncio
async def test_index_repo(client):
    result = await client.index_repo("test-repo", "/path/to/repo")
    assert "review_tasks" in result
    assert len(result["review_tasks"]) == 1


@pytest.mark.asyncio
async def test_get_tasks(client):
    tasks = await client.get_tasks("test-repo")
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_get_task_package(client):
    pkg = await client.get_task_package("task_1", "test-repo")
    assert pkg["task_id"] == "task_1"
    assert pkg["task_type"] == "entrypoint_review"


@pytest.mark.asyncio
async def test_get_graph_slice(client):
    graph = await client.get_graph_slice("task_1", "test-repo", depth=2)
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["name"] == "login"


@pytest.mark.asyncio
async def test_get_node_detail(client):
    detail = await client.get_node_detail("test-repo", symbol_name="login")
    assert detail is not None
    assert detail["name"] == "login"


@pytest.mark.asyncio
async def test_get_file_snippet(client):
    snippet = await client.get_file_snippet("test-repo", "app/api/auth.py")
    assert snippet["file_path"] == "app/api/auth.py"


@pytest.mark.asyncio
async def test_get_callees(client):
    callees = await client.get_callees("test-repo", symbol_name="login")
    assert callees[0]["name"] == "authenticate"


@pytest.mark.asyncio
async def test_get_callers(client):
    callers = await client.get_callers("test-repo", symbol_name="login")
    assert callers[0]["name"] == "main"


@pytest.mark.asyncio
async def test_get_related_context(client):
    result = await client.get_related_context("test-repo", "task_1")
    assert "related_files" in result


@pytest.mark.asyncio
async def test_submit_feedback(client):
    result = await client.submit_feedback(
        "test-repo",
        "task_1",
        agent="test-agent",
        status="completed",
        context_sufficient=True,
        feedback_type="function_logic_review",
    )
    assert result["accepted"] is True
    assert result["next_action"] == "continue_downstream"


@pytest.mark.asyncio
async def test_client_context_manager():
    transport = httpx.MockTransport(_mock_handler)
    async with ContextAPIClient("http://testserver") as client:
        client._client = httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        )
        result = await client.index_repo("test-repo", "/path")
        assert "review_tasks" in result
