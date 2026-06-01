from pathlib import Path

from fastapi.testclient import TestClient

from repo_context.api.app import app


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REPO = ROOT / "tests" / "fixtures" / "sample_repo"


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_context_api_file_snippet_and_path_traversal(tmp_path: Path) -> None:
    client = _indexed_client(tmp_path, "api-context-file")

    response = client.get(
        "/context/file-snippet",
        params={
            "repo_id": "api-context-file",
            "file_path": "app/api/auth.py",
            "start_line": 1,
            "end_line": 5,
            "task_id": "task_route_post_login",
            "review_dimension": "security",
        },
    )
    blocked = client.get(
        "/context/file-snippet",
        params={
            "repo_id": "api-context-file",
            "file_path": "../../secret.txt",
            "start_line": 1,
            "end_line": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["file_path"] == "app/api/auth.py"
    assert data["start_line"] == 1
    assert data["end_line"] == 5
    assert data["content"]
    assert blocked.status_code == 400


def test_context_api_node_detail_callees_and_usage(tmp_path: Path) -> None:
    client = _indexed_client(tmp_path, "api-context-node")

    detail_response = client.get(
        "/context/node-detail",
        params={
            "repo_id": "api-context-node",
            "symbol_name": "login",
            "task_id": "task_route_post_login",
            "review_dimension": "security",
        },
    )
    detail = detail_response.json()
    callees_response = client.get(
        "/context/callees",
        params={
            "repo_id": "api-context-node",
            "node_id": detail["node_id"],
            "depth": 1,
            "task_id": "task_route_post_login",
            "review_dimension": "security",
        },
    )
    callers_response = client.get(
        "/context/callers",
        params={
            "repo_id": "api-context-node",
            "symbol_name": "authenticate",
            "depth": 1,
            "task_id": "task_route_post_login",
            "review_dimension": "security",
        },
    )
    coverage = client.get("/demo/api-context-node/coverage").json()["usage_coverage_report"]

    assert detail_response.status_code == 200
    assert detail["file_path"] == "app/api/auth.py"
    assert detail["start_line"] > 0
    assert "def login" in detail["code"]
    assert callees_response.status_code == 200
    assert callees_response.json()
    assert callers_response.status_code == 200
    assert callers_response.json()
    assert any(
        item["tool_name"] == "get_node_detail" and item["target_type"] == "symbol"
        for item in coverage["usage_records"]
    )
    assert any(
        item["tool_name"] == "get_callees" and item["target_type"] == "graph"
        for item in coverage["usage_records"]
    )
    assert any(
        item["tool_name"] == "get_callers" and item["target_type"] == "graph"
        for item in coverage["usage_records"]
    )


def test_context_api_related_context_and_task_package_are_local(tmp_path: Path) -> None:
    client = _indexed_client(tmp_path, "api-context-package")
    tasks = client.get("/demo/api-context-package/tasks").json()["review_tasks"]
    task_package = next(item for item in tasks if item["task_id"] == "task_route_post_login")
    full_package_response = client.get(
        "/context/task-package/task_route_post_login",
        params={"repo_id": "api-context-package"},
    )
    related_response = client.post(
        "/context/related-context",
        json={
            "repo_id": "api-context-package",
            "task_id": "task_route_post_login",
            "target_file": "app/api/auth.py",
            "review_dimension": "security",
            "tags": ["api_entry", "auth"],
            "max_depth": 1,
            "max_files": 2,
        },
    )
    assert full_package_response.status_code == 200
    full_package = full_package_response.json()
    assert full_package["initial_context"]
    assert full_package["available_tools"]
    assert full_package["context_policy"]["allow_expand"] is True
    assert full_package["initial_context"]["type"] == "task_entry"
    assert full_package["initial_context"]["suggested_next_tool"] == "get_task_graph_slice"
    assert "call_graph_slice" not in full_package["initial_context"]
    graph_response = client.get(
        "/context/tasks/task_route_post_login/graph-slice",
        params={"repo_id": "api-context-package", "depth": 1},
    )
    assert graph_response.status_code == 200
    task_graph = graph_response.json()
    assert task_graph["graph_scope"] == "task-local"
    assert task_graph["nodes"]
    assert "call_graph_slice" not in task_package["initial_context"]
    assert len(task_graph["nodes"]) < 20

    assert related_response.status_code == 200
    related = related_response.json()
    coverage = client.get("/demo/api-context-package/coverage").json()["usage_coverage_report"]
    assert related["snippets"]
    assert related["related_symbols"]
    assert related["call_graph_slice"]["graph_scope"] == "local"
    assert len(related["related_files"]) <= 2
    assert len(related["call_graph_slice"]["nodes"]) <= len(task_graph["nodes"])
    assert any(
        item["tool_name"] == "get_related_context"
        and item["target_type"] == "batch_context"
        for item in coverage["usage_records"]
    )
    assert any(
        item["tool_name"] == "get_task_graph_slice"
        and item["target_type"] == "graph_slice"
        for item in coverage["usage_records"]
    )


def _indexed_client(tmp_path: Path, repo_id: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/context/index",
        json={
            "repo_id": repo_id,
            "repo_path": str(SAMPLE_REPO),
            "db_path": str(tmp_path / f"{repo_id}.db"),
        },
    )
    assert response.status_code == 200
    return client
