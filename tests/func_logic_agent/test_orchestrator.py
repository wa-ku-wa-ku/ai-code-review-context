from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from func_logic_agent.config import AgentConfig
from func_logic_agent.models import (
    Finding,
    GatheredContext,
    LLMJudgmentResult,
    RuleScreeningResult,
)
from func_logic_agent.orchestrator import FuncLogicAgent


def _make_mock_transport():
    """Create a mock transport that handles all endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method

        if path == "/context/index" and method == "POST":
            return httpx.Response(200, json={
                "review_tasks": [
                    {
                        "task_id": "task_1",
                        "task_type": "entrypoint_review",
                        "review_dimension": "function_logic",
                        "priority": "high",
                        "target": {"file_path": "app/api/auth.py", "symbols": ["login"]},
                    },
                    {
                        "task_id": "task_2",
                        "task_type": "file_review",
                        "review_dimension": "function_logic",
                        "priority": "low",
                        "target": {"file_path": "app/utils.py"},
                    },
                    {
                        "task_id": "task_3",
                        "task_type": "entrypoint_review",
                        "review_dimension": "security",
                        "priority": "high",
                        "target": {"file_path": "app/api/auth.py"},
                    },
                ],
                "repo_summary": {"framework": "fastapi"},
            })

        if path.startswith("/context/task-package/"):
            return httpx.Response(200, json={
                "task_id": "task_1",
                "task_type": "entrypoint_review",
                "target": {"file_path": "app/api/auth.py", "symbols": ["login"]},
                "priority": "high",
                "review_dimension": "function_logic",
                "context_policy": {"max_graph_depth": 2},
            })

        if "/graph-slice" in path:
            return httpx.Response(200, json={
                "task_id": "task_1",
                "nodes": [
                    {
                        "node_id": "n1", "name": "login",
                        "relation_to_target": "target",
                        "priority": 100, "risk_score": 40,
                    },
                ],
                "edges": [],
                "boundary_nodes": [],
            })

        if path == "/context/node-detail":
            return httpx.Response(200, json={
                "node_id": "n1", "name": "login", "source": "def login(): pass"
            })

        if path == "/context/file-snippet":
            return httpx.Response(200, json={
                "file_path": "app/api/auth.py", "content": "def login(): pass"
            })

        if path == "/context/task-feedback" and method == "POST":
            body = json.loads(request.content)
            return httpx.Response(200, json={
                "accepted": True,
                "task_id": body.get("task_id"),
                "status": body.get("status"),
                "next_action": "continue_downstream",
            })

        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def agent(config):
    agent = FuncLogicAgent(config)
    transport = _make_mock_transport()
    agent.client._client = httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    )
    return agent


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_run_filters_function_logic_tasks(self, agent):
        """Only function_logic tasks should be processed."""
        mock_judge = MagicMock()
        mock_judge.return_value = LLMJudgmentResult(
            has_issue=False, confidence=0.9, findings=[]
        )
        agent.llm_judge.judge = AsyncMock(return_value=LLMJudgmentResult(
            has_issue=False, confidence=0.9, findings=[]
        ))

        results = await agent.run("/path/to/repo")

        task_ids = [r.task_id for r in results]
        assert "task_1" in task_ids
        assert "task_2" in task_ids
        assert "task_3" not in task_ids  # security dimension, not function_logic

    @pytest.mark.asyncio
    async def test_run_submits_feedback(self, agent):
        """Completed tasks should have feedback submitted."""
        agent.llm_judge.judge = AsyncMock(return_value=LLMJudgmentResult(
            has_issue=False, confidence=0.9, findings=[]
        ))

        results = await agent.run("/path/to/repo")

        completed = [r for r in results if r.status == "completed"]
        assert len(completed) > 0

    @pytest.mark.asyncio
    async def test_run_handles_llm_failure(self, agent):
        """LLM errors should result in blocked status."""
        agent.llm_judge.judge = AsyncMock(return_value=LLMJudgmentResult(
            has_issue=False,
            confidence=0.0,
            findings=[],
            parse_error="LLM API error: connection refused",
        ))

        results = await agent.run("/path/to/repo")

        blocked = [r for r in results if r.status == "blocked"]
        assert len(blocked) > 0

    @pytest.mark.asyncio
    async def test_run_orders_by_priority(self, agent):
        """High priority tasks should be processed before low."""
        call_order = []
        original_process = agent._process_task

        async def track_process(task):
            call_order.append(task.get("priority", "?"))
            return await original_process(task)

        agent._process_task = track_process
        agent.llm_judge.judge = AsyncMock(return_value=LLMJudgmentResult(
            has_issue=False, confidence=0.9, findings=[]
        ))

        await agent.run("/path/to/repo")

        # high should come before low
        if "high" in call_order and "low" in call_order:
            assert call_order.index("high") < call_order.index("low")

    @pytest.mark.asyncio
    async def test_feedback_loop_requests_file_snippet_and_rejudges(self, agent):
        """Low-confidence findings should request actionable file context."""
        agent.config.max_context_retries = 1
        agent.client.submit_feedback = AsyncMock(side_effect=[
            {"next_action": "provide_more_context"},
            {"next_action": "continue_downstream"},
        ])
        agent._gather_context = AsyncMock(return_value=GatheredContext())
        agent.llm_judge.judge_followup = AsyncMock(return_value=LLMJudgmentResult(
            has_issue=False,
            confidence=0.9,
            findings=[],
        ))

        result = await agent._submit_and_loop(
            "task_1",
            {"task_id": "task_1", "target": {"file_path": "app/api/auth.py"}},
            {"nodes": []},
            GatheredContext(),
            RuleScreeningResult(),
            LLMJudgmentResult(
                has_issue=True,
                confidence=0.4,
                findings=[
                    Finding(
                        title="Suspected issue",
                        description="Need surrounding code",
                        severity="medium",
                        file_path="app/api/auth.py",
                        start_line=10,
                        end_line=12,
                    )
                ],
            ),
        )

        first_feedback = agent.client.submit_feedback.call_args_list[0].kwargs
        requested = first_feedback["requested_context"][0]
        assert requested["type"] == "file_snippet"
        assert requested["file_path"] == "app/api/auth.py"
        assert requested["start_line"] == 1
        assert requested["end_line"] == 32
        assert agent.llm_judge.judge_followup.await_count == 1
        assert "requested_description" in agent.llm_judge.judge_followup.call_args.kwargs
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_zero_context_retries_still_submits_feedback(self, agent):
        """Disabling retries should still submit the first feedback payload."""
        agent.config.max_context_retries = 0
        agent.client.submit_feedback = AsyncMock(
            return_value={"next_action": "provide_more_context"}
        )
        agent._gather_context = AsyncMock(return_value=GatheredContext())

        result = await agent._submit_and_loop(
            "task_1",
            {"task_id": "task_1", "target": {"file_path": "app/api/auth.py"}},
            {"nodes": []},
            GatheredContext(),
            RuleScreeningResult(),
            LLMJudgmentResult(
                has_issue=True,
                confidence=0.4,
                findings=[
                    Finding(
                        title="Suspected issue",
                        description="Need surrounding code",
                        severity="medium",
                        file_path="app/api/auth.py",
                    )
                ],
            ),
        )

        assert agent.client.submit_feedback.await_count == 1
        assert agent._gather_context.await_count == 0
        assert result.status == "completed"
        assert result.context_sufficient is False


class TestGatherContext:
    @pytest.mark.asyncio
    async def test_gather_context_deduplicates(self, agent):
        """Gathered context should not fetch the same node twice."""
        task_package = {
            "task_id": "task_1",
            "target": {"file_path": "app/api/auth.py"},
        }
        graph_slice = {
            "nodes": [
                {
                    "node_id": "n1", "name": "login",
                    "relation_to_target": "target",
                    "priority": 100, "risk_score": 0,
                },
            ],
            "edges": [],
        }

        ctx = await agent._gather_context(task_package, graph_slice)

        # Should have fetched node detail and file snippet
        assert len(ctx.fetched_node_ids) >= 1
        assert len(ctx.fetched_file_ranges) >= 1

        # Second call should not duplicate
        ctx2 = await agent._gather_context(task_package, graph_slice)
        ctx.merge(ctx2)
        # Fetched sets should still be reasonable (no infinite growth)
        assert len(ctx.fetched_node_ids) <= 5
