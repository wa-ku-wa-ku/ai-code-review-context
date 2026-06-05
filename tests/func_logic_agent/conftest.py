from __future__ import annotations

from typing import Any

import pytest

from func_logic_agent.config import AgentConfig


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig(
        repo_id="test-repo",
        context_api_base="http://testserver",
        llm_model="claude-sonnet-4-20250514",
    )


@pytest.fixture
def sample_task_package() -> dict[str, Any]:
    return {
        "task_id": "task_route_post_login",
        "repo_id": "test-repo",
        "task_type": "entrypoint_review",
        "target": {
            "type": "route",
            "file_path": "app/api/auth.py",
            "symbols": ["login"],
        },
        "priority": "high",
        "review_dimension": "function_logic",
        "focus_points": ["input validation", "error handling"],
        "tags": ["auth"],
        "reason": "API entrypoint detected",
        "initial_context": {
            "type": "task_entry",
            "suggested_next_tool": "get_task_graph_slice",
            "suggested_next_params": {"task_id": "task_route_post_login", "depth": 2},
        },
        "context_policy": {
            "max_depth": 2,
            "max_snippet_lines": 120,
            "max_files": 5,
            "max_graph_depth": 2,
        },
    }


@pytest.fixture
def sample_graph_slice() -> dict[str, Any]:
    return {
        "task_id": "task_route_post_login",
        "target": "login",
        "depth": 2,
        "nodes": [
            {
                "node_id": "app.api.auth.login",
                "name": "login",
                "type": "function",
                "file_path": "app/api/auth.py",
                "start_line": 5,
                "end_line": 12,
                "relation_to_target": "target",
                "priority": 100,
                "risk_score": 40,
                "reason": "auth-related function",
            },
            {
                "node_id": "app.services.user_service.authenticate",
                "name": "authenticate",
                "type": "function",
                "file_path": "app/services/user_service.py",
                "start_line": 3,
                "end_line": 8,
                "relation_to_target": "direct_callee",
                "priority": 85,
                "risk_score": 20,
                "reason": "called by login",
            },
            {
                "node_id": "app.repositories.user_repo.find_by_username",
                "name": "find_by_username",
                "type": "function",
                "file_path": "app/repositories/user_repo.py",
                "start_line": 1,
                "end_line": 5,
                "relation_to_target": "indirect",
                "depth": 2,
                "priority": 55,
                "risk_score": 0,
                "reason": "called by authenticate",
            },
        ],
        "edges": [
            {"source": "app.api.auth.login", "target": "app.services.user_service.authenticate", "type": "calls"},
            {"source": "app.services.user_service.authenticate", "target": "app.repositories.user_repo.find_by_username", "type": "calls"},
        ],
        "boundary_nodes": [],
        "graph_scope": "task-local",
    }


@pytest.fixture
def sample_node_detail() -> dict[str, Any]:
    return {
        "node_id": "app.api.auth.login",
        "name": "login",
        "type": "function",
        "file_path": "app/api/auth.py",
        "start_line": 5,
        "end_line": 12,
        "source": (
            "@router.post('/login')\n"
            "async def login(username: str, password: str):\n"
            "    user = authenticate(username, password)\n"
            "    if not user:\n"
            "        raise HTTPException(status_code=401)\n"
            "    return {'token': '...'}"
        ),
        "callers": [],
        "callees": [
            {"name": "authenticate", "file_path": "app/services/user_service.py"}
        ],
    }


@pytest.fixture
def sample_llm_response_json() -> str:
    return """{
        "has_issue": false,
        "confidence": 0.85,
        "findings": []
    }"""


@pytest.fixture
def sample_llm_response_with_findings() -> str:
    return """{
        "has_issue": true,
        "confidence": 0.9,
        "findings": [
            {
                "title": "Missing null check",
                "description": "authenticate may return None",
                "severity": "high",
                "file_path": "app/api/auth.py",
                "start_line": 7,
                "end_line": 8,
                "evidence": "user = authenticate(...); if not user",
                "suggestion": "Add explicit None check"
            }
        ]
    }"""
