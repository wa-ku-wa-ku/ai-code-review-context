import json
from pathlib import Path

import pytest

from repo_context.index.index_builder import build_index
from repo_context.service.context_pack_builder import ContextPackBuilder
from repo_context.service.context_service import ContextService
from repo_context.task.review_task_generator import ReviewTaskGenerator


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REPO = ROOT / "tests" / "fixtures" / "sample_repo"


def test_directional_task_package_contains_context_controls(
    task_generator: ReviewTaskGenerator,
) -> None:
    task = next(item for item in task_generator.generate().review_tasks if item.task_id == "task_route_post_login")
    package = task.to_dict()

    assert package["review_dimension"] == "security"
    assert package["target"]["file_path"] == "app/api/auth.py"
    assert package["initial_context"]["file_snippets"]
    assert package["initial_context"]["call_graph_slice"]["graph_scope"] == "local"
    assert "get_file_snippet" in package["available_tools"]
    assert "get_node_detail" in package["available_tools"]
    assert "get_callees" in package["available_tools"]
    assert "get_related_context" in package["available_tools"]
    assert package["context_policy"]["allow_expand"] is True
    _assert_json_serializable(package)


def test_task_local_graph_slice_is_limited_to_task_nodes(
    context_service: ContextService,
    task_generator: ReviewTaskGenerator,
) -> None:
    task = next(item for item in task_generator.generate().review_tasks if item.task_id == "task_route_post_login")
    graph = task.initial_context["call_graph_slice"]
    full_edge_count = len(context_service.store.list_code_edges(context_service.repo_id))

    assert graph["graph_scope"] == "local"
    assert graph["depth"] <= 2
    assert len(graph["edges"]) <= full_edge_count
    assert "nodes" in graph
    assert "edges" in graph
    _assert_json_serializable(graph)


def test_security_context_prefers_auth_related_symbols(task_generator: ReviewTaskGenerator) -> None:
    task = next(item for item in task_generator.generate().review_tasks if item.task_id == "task_route_post_login")
    package_text = json.dumps(task.initial_context, ensure_ascii=False).lower()

    assert "auth" in package_text
    assert "login" in package_text


def test_function_logic_context_contains_call_graph(task_generator: ReviewTaskGenerator) -> None:
    task = next(item for item in task_generator.generate().review_tasks if item.task_type == "module_review")

    assert task.review_dimension == "function_logic"
    assert "call_graph_slice" in task.initial_context


def test_builder_returns_empty_graph_for_missing_target(context_service: ContextService) -> None:
    builder = ContextPackBuilder(context_service)

    graph = builder.build_task_local_graph(
        {
            "task_id": "missing",
            "target": {"type": "file", "file_path": "app/missing.py", "symbols": ["missing"]},
        }
    )

    assert graph["nodes"] == []
    assert graph["edges"] == []


def _assert_json_serializable(value: object) -> None:
    json.dumps(value, ensure_ascii=False)


@pytest.fixture()
def context_service(tmp_path: Path) -> ContextService:
    db_path = tmp_path / "context.db"
    build_index("sample-repo", SAMPLE_REPO, db_path)
    return ContextService("sample-repo", SAMPLE_REPO, db_path)


@pytest.fixture()
def task_generator(context_service: ContextService) -> ReviewTaskGenerator:
    return ReviewTaskGenerator(context_service)
