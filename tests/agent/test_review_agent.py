import json

import httpx
import pytest
from fastapi.testclient import TestClient

from review_agent.config import DownstreamAgentConfig, LLMConfigError
from review_agent.clients import ContextApiClient, LLMReviewClient, ReviewResult
from review_agent.config import LLMApiConfig
from review_agent.core import BasicReviewAgent, ContextToolbelt, FunctionLogicAgent


def test_context_api_client_calls_standard_flow() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/context/task-package/task_1":
            return httpx.Response(200, json={"task_id": "task_1"})
        if request.url.path == "/context/tasks":
            return httpx.Response(200, json={"tasks": [{"task_id": "task_1"}]})
        if request.url.path == "/context/tasks/task_1/graph-slice":
            return httpx.Response(200, json={"nodes": []})
        if request.url.path == "/context/related-context":
            return httpx.Response(200, json={"snippets": []})
        if request.url.path == "/context/task-feedback":
            return httpx.Response(200, json={"accepted": True})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http_client = httpx.Client(
        base_url="http://context.test",
        transport=httpx.MockTransport(handler),
    )
    client = ContextApiClient("http://context.test", client=http_client)

    assert client.get_task_package(repo_id="repo-1", task_id="task_1")["task_id"] == "task_1"
    assert client.list_tasks(repo_id="repo-1", review_dimension="security")["tasks"][0]["task_id"] == "task_1"
    assert client.get_task_graph_slice(repo_id="repo-1", task_id="task_1")["nodes"] == []
    assert client.get_related_context(
        repo_id="repo-1",
        task_id="task_1",
        target_file="app/api/auth.py",
        review_dimension="security",
    )["snippets"] == []
    assert client.submit_task_feedback(
        repo_id="repo-1",
        task_id="task_1",
        agent="basic-agent",
        status="completed",
        context_sufficient=True,
        feedback_type="task_status",
    )["accepted"] is True

    assert [request.url.path for request in requests] == [
        "/context/task-package/task_1",
        "/context/tasks",
        "/context/tasks/task_1/graph-slice",
        "/context/related-context",
        "/context/task-feedback",
    ]


def test_llm_review_client_parses_openai_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/chat/completions"
        assert body["model"] == "test-model"
        content = json.dumps(
            {
                "status": "completed",
                "context_sufficient": True,
                "message": "done",
                "requested_context": [],
                "downstream_result_ref": "result-1",
            }
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    llm = LLMReviewClient(
        LLMApiConfig(
            provider="openai",
            base_url="http://llm.test",
            api_key="test-key",
            model="test-model",
        ),
        client=httpx.Client(base_url="http://llm.test", transport=httpx.MockTransport(handler)),
    )

    result = llm.review_task(
        task_package={"task_id": "task_1"},
        graph_slice={"nodes": []},
        related_context={"snippets": []},
    )

    assert result.status == "completed"
    assert result.context_sufficient is True
    assert result.downstream_result_ref == "result-1"


def test_basic_review_agent_runs_task_and_submits_feedback() -> None:
    context_client = _FakeContextClient()
    agent = BasicReviewAgent(
        agent_name="basic-agent",
        context_client=context_client,
        llm_client=_FakeLLMClient(),
    )

    result = agent.run_task(repo_id="repo-1", task_id="task_1")

    assert result["feedback"]["accepted"] is True
    assert result["review_result"]["status"] == "completed"
    assert context_client.feedback_payload["agent"] == "basic-agent"
    assert context_client.feedback_payload["feedback_type"] == "task_status"
    assert context_client.calls == [
        "get_task_package",
        "get_task_graph_slice",
        "get_related_context",
        "submit_task_feedback",
    ]


def test_function_logic_agent_lists_and_runs_task_with_context_tools() -> None:
    context_client = _FakeContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeLLMClient(),
    )

    tasks = agent.list_tasks(repo_id="repo-1")
    result = agent.run_next_task(repo_id="repo-1")

    assert tasks[0]["task_id"] == "task_1"
    assert result is not None
    assert result["review_dimension"] == "function_logic"
    assert result["feedback"]["accepted"] is True
    assert {call["name"] for call in result["tool_calls"]} == {
        "get_file_snippet",
        "get_node_detail",
        "get_callees",
        "get_callers",
    }
    assert context_client.calls == [
        "list_tasks",
        "list_tasks",
        "get_task_package",
        "get_task_graph_slice",
        "get_related_context",
        "get_file_snippet",
        "get_node_detail",
        "get_callees",
        "get_callers",
        "submit_task_feedback",
    ]


def test_function_logic_agent_runs_ai_decided_tool_trace() -> None:
    context_client = _FakeContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeTraceLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_1", max_steps=3)

    event_types = [event["type"] for event in result["trace"]]
    assert "ai_request" in event_types
    assert "ai_response" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-2:] == ["final_result", "task_feedback"]
    assert result["final_result"]["status"] == "completed"
    assert result["final_result"]["summary"] == "create_user persists the requested user data."
    assert result["final_result"]["findings"][0]["title"] == "No functional issue found"
    assert context_client.calls == [
        "get_task_package",
        "get_task_graph_slice",
        "get_node_detail",
        "submit_task_feedback",
    ]


def test_function_logic_agent_blocks_weak_final_trace_output() -> None:
    context_client = _FakeContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeWeakFinalLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_1", max_steps=1)

    assert result["final_result"]["status"] == "blocked"
    assert result["final_result"]["context_sufficient"] is False
    assert result["final_result"]["parser_warnings"] == ["missing summary", "missing findings"]
    assert "invalid_model_output" in result["final_result"]["message"]
    assert context_client.feedback_payload["status"] == "blocked"
    assert context_client.feedback_payload["need_more_context"] is True


def test_function_logic_agent_fills_missing_tool_arguments_from_task_runtime() -> None:
    context_client = _FakeContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeMissingToolArgsLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_1", max_steps=4)
    tool_calls = [event for event in result["trace"] if event["type"] == "tool_call"]

    assert tool_calls[0]["payload"]["tool_name"] == "get_node_detail"
    assert tool_calls[0]["payload"]["tool_args"]["symbol_name"] == "create_user"
    assert tool_calls[1]["payload"]["tool_name"] == "get_file_snippet"
    assert tool_calls[1]["payload"]["tool_args"]["file_path"] == "app/services/user_service.py"
    assert tool_calls[1]["payload"]["tool_args"]["start_line"] == 1
    assert tool_calls[1]["payload"]["tool_args"]["end_line"] == 80
    assert tool_calls[2]["payload"]["tool_name"] == "get_callees"
    assert tool_calls[2]["payload"]["tool_args"]["symbol_name"] == "create_user"
    assert tool_calls[2]["payload"]["tool_args"]["depth"] == 3


def test_function_logic_agent_does_not_preload_related_context_for_module_task() -> None:
    context_client = _FakeModuleContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeTraceLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_module_app_core", max_steps=3)

    assert result["related_context"]["preloaded"] is False
    assert "get_related_context" not in context_client.calls
    assert result["final_result"]["status"] == "completed"


def test_function_logic_agent_records_tool_error_when_required_args_are_missing() -> None:
    context_client = _FakeModuleContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeMissingTargetFileLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_module_app_core", max_steps=2)
    tool_results = [event for event in result["trace"] if event["type"] == "tool_result"]
    related_error = next(event for event in tool_results if event["payload"].get("name") == "get_related_context")

    assert related_error["payload"]["error"] == "missing required tool argument: target_file"
    assert "get_related_context" not in context_client.calls


def test_llm_review_client_blocks_unstructured_final_decision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {
                "action": "final",
                "status": "completed",
                "context_sufficient": True,
                "message": "task processed",
            }
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    llm = LLMReviewClient(
        LLMApiConfig(
            provider="openai",
            base_url="http://llm.test",
            api_key="test-key",
            model="test-model",
        ),
        client=httpx.Client(base_url="http://llm.test", transport=httpx.MockTransport(handler)),
    )

    decision = llm.decide_next_action(
        task_package={"task_id": "task_1"},
        graph_slice={"nodes": []},
        related_context={"snippets": []},
        trace=[],
        available_tools=["get_node_detail"],
    )

    assert decision["status"] == "blocked"
    assert decision["context_sufficient"] is False
    assert decision["parser_warnings"] == ["missing summary", "missing findings"]
    assert decision["raw_content"]


def test_llm_review_client_accepts_wrapped_call_tool_decision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {
                "call_tool": {
                    "action": "call_tool",
                    "tool_name": "get_file_snippet",
                    "tool_args": {
                        "file_path": "app/core/__init__.py",
                        "start_line": 1,
                        "end_line": 120,
                    },
                    "reason": "Need module entry source.",
                }
            }
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    llm = LLMReviewClient(
        LLMApiConfig(
            provider="openai",
            base_url="http://llm.test",
            api_key="test-key",
            model="test-model",
        ),
        client=httpx.Client(base_url="http://llm.test", transport=httpx.MockTransport(handler)),
    )

    decision = llm.decide_next_action(
        task_package={"task_id": "task_1"},
        graph_slice={"nodes": []},
        related_context={"snippets": []},
        trace=[],
        available_tools=["get_file_snippet"],
    )

    assert decision["action"] == "call_tool"
    assert decision["tool_name"] == "get_file_snippet"
    assert decision["tool_args"]["file_path"] == "app/core/__init__.py"


def test_function_logic_agent_deduplicates_parser_warnings() -> None:
    context_client = _FakeContextClient()
    agent = FunctionLogicAgent(
        agent_name="function-logic-agent",
        context_client=context_client,
        llm_client=_FakeWeakFinalWithWarningsLLMClient(),
    )

    result = agent.run_task_trace(repo_id="repo-1", task_id="task_1", max_steps=1)

    assert result["final_result"]["parser_warnings"] == ["missing summary", "missing findings"]


def test_llm_action_prompt_includes_tool_parameter_contract() -> None:
    seen_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_body.update(json.loads(request.content))
        content = json.dumps(
            {
                "action": "final",
                "status": "blocked",
                "context_sufficient": False,
                "summary": "Need more context.",
                "findings": [{"title": "Need context", "severity": "info"}],
                "checked_context": ["task_package"],
                "remaining_questions": ["Need node detail"],
            }
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    llm = LLMReviewClient(
        LLMApiConfig(
            provider="openai",
            base_url="http://llm.test",
            api_key="test-key",
            model="test-model",
        ),
        client=httpx.Client(base_url="http://llm.test", transport=httpx.MockTransport(handler)),
    )

    llm.decide_next_action(
        task_package={"task_id": "task_1"},
        graph_slice={"nodes": []},
        related_context={"snippets": []},
        trace=[],
        available_tools=["get_node_detail"],
    )

    prompt = seen_body["messages"][1]["content"]  # type: ignore[index]
    payload = json.loads(prompt)
    assert payload["tool_parameter_contract"]["agent_auto_fills"] == [
        "repo_id",
        "task_id",
        "review_dimension",
        "tags",
    ]
    assert payload["tool_parameter_contract"]["get_node_detail"]["defaults"]["symbol_name"]
    assert "Do not wrap" in payload["output_rule"]


def test_agent_demo_page_loads() -> None:
    from review_agent.api.app import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Function Logic Agent Trace" in response.text
    assert "/agent/function-logic/run" in response.text


def test_agent_demo_run_endpoint_returns_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    import review_agent.api.app as app_module

    class FakeAgent:
        @classmethod
        def from_env(cls) -> "FakeAgent":
            return cls()

        def run_task_trace(self, **kwargs: object) -> dict[str, object]:
            return {
                "repo_id": kwargs["repo_id"],
                "task_id": kwargs["task_id"],
                "trace": [{"type": "ai_response", "payload": {"action": "final"}}],
                "final_result": {
                    "status": "completed",
                    "summary": "done",
                    "findings": [],
                    "parser_warnings": [],
                },
            }

    monkeypatch.setattr(app_module, "FunctionLogicAgent", FakeAgent)
    client = TestClient(app_module.app)

    response = client.post(
        "/agent/function-logic/run",
        json={"repo_id": "repo-1", "task_id": "task_1"},
    )

    assert response.status_code == 200
    assert response.json()["trace"][0]["type"] == "ai_response"


def test_context_toolbelt_exposes_all_context_interfaces() -> None:
    toolbelt = ContextToolbelt(_FakeContextClient())

    assert toolbelt.available_tools == [
        "build_index",
        "get_callees",
        "get_callers",
        "get_file_snippet",
        "get_node_detail",
        "get_related_context",
        "get_task_graph_slice",
        "get_task_package",
        "list_tasks",
        "submit_task_feedback",
    ]


def test_config_from_env_requires_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "REVIEW_AGENT_PROVIDER",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(LLMConfigError):
        DownstreamAgentConfig.from_env()


def test_config_from_env_uses_deepseek_v4_flash_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVIEW_AGENT_NAME", raising=False)
    monkeypatch.delenv("REVIEW_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("REVIEW_AGENT_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    config = DownstreamAgentConfig.from_env()

    assert config.agent_name == "function-logic-agent"
    assert config.llm_api.provider == "deepseek"
    assert config.llm_api.model == "deepseek-v4-flash"


def test_review_agent_keeps_runtime_layers_separated() -> None:
    from pathlib import Path

    import review_agent

    root = Path(review_agent.__path__[0])
    assert root.parent.name == "agent"
    package_dirs = {path.name for path in root.iterdir() if path.is_dir()}
    assert {"clients", "config", "core"}.issubset(package_dirs)
    assert "frontend" not in package_dirs


class _FakeContextClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.feedback_payload: dict[str, object] = {}

    def build_index(self, *, repo_id: str, repo_path: str, db_path: str | None = None) -> dict[str, object]:
        self.calls.append("build_index")
        return {"repo_id": repo_id, "review_tasks": [{"task_id": "task_1"}]}

    def list_tasks(self, *, repo_id: str, review_dimension: str) -> dict[str, object]:
        self.calls.append("list_tasks")
        return {
            "repo_id": repo_id,
            "review_dimension": review_dimension,
            "tasks": [{"task_id": "task_1", "status": "pending"}],
        }

    def get_task_package(self, *, repo_id: str, task_id: str) -> dict[str, object]:
        self.calls.append("get_task_package")
        return {
            "task_id": task_id,
            "review_dimension": "function_logic",
            "target": {"file_path": "app/services/user_service.py", "symbols": ["create_user"]},
            "tags": ["service"],
        }

    def get_task_graph_slice(self, *, repo_id: str, task_id: str, depth: int) -> dict[str, object]:
        self.calls.append("get_task_graph_slice")
        return {"nodes": [{"name": "login"}], "depth": depth}

    def get_related_context(
        self,
        *,
        repo_id: str,
        task_id: str,
        target_file: str | None,
        review_dimension: str | None,
        tags: list[str],
        max_depth: int,
        max_files: int,
    ) -> dict[str, object]:
        self.calls.append("get_related_context")
        return {"target_file": target_file, "snippets": []}

    def get_file_snippet(
        self,
        *,
        repo_id: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, object]:
        self.calls.append("get_file_snippet")
        return {"file_path": file_path, "content": "def create_user(): ..."}

    def get_node_detail(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> dict[str, object]:
        self.calls.append("get_node_detail")
        return {"symbol_name": symbol_name, "code": "def create_user(): ..."}

    def get_callees(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append("get_callees")
        return [{"source": symbol_name, "target": "repo.save"}]

    def get_callers(
        self,
        *,
        repo_id: str,
        node_id: str | None = None,
        symbol_name: str | None = None,
        depth: int = 1,
        task_id: str | None = None,
        review_dimension: str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append("get_callers")
        return [{"source": "api.create_user", "target": symbol_name}]

    def submit_task_feedback(self, **payload: object) -> dict[str, object]:
        self.calls.append("submit_task_feedback")
        self.feedback_payload = dict(payload)
        return {"accepted": True, **payload}


class _FakeModuleContextClient(_FakeContextClient):
    def get_task_package(self, *, repo_id: str, task_id: str) -> dict[str, object]:
        self.calls.append("get_task_package")
        return {
            "task_id": task_id,
            "task_type": "module_review",
            "review_dimension": "function_logic",
            "target": {"module_path": "app/core"},
            "recommended_nodes": ["load_settings"],
            "tags": ["module"],
        }

    def get_related_context(
        self,
        *,
        repo_id: str,
        task_id: str,
        target_file: str | None,
        review_dimension: str | None,
        tags: list[str],
        max_depth: int,
        max_files: int,
    ) -> dict[str, object]:
        if not target_file:
            raise AssertionError("module trace should not call related_context without target_file")
        return super().get_related_context(
            repo_id=repo_id,
            task_id=task_id,
            target_file=target_file,
            review_dimension=review_dimension,
            tags=tags,
            max_depth=max_depth,
            max_files=max_files,
        )


class _FakeLLMClient:
    def review_task(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        tool_results: list[dict[str, object]] | None = None,
    ) -> ReviewResult:
        assert tool_results is None or tool_results
        return ReviewResult(
            status="completed",
            context_sufficient=True,
            message="done",
            downstream_result_ref="result-1",
        )


class _FakeTraceLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def decide_next_action(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        trace: list[dict[str, object]],
        available_tools: list[str],
    ) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return {
                "action": "call_tool",
                "tool_name": "get_node_detail",
                "tool_args": {"symbol_name": "create_user"},
                "reason": "Need target function body before final reasoning.",
            }
        return {
            "action": "final",
            "status": "completed",
            "context_sufficient": True,
            "summary": "create_user persists the requested user data.",
            "findings": [
                {
                    "title": "No functional issue found",
                    "severity": "info",
                    "evidence": {
                        "file_path": "app/services/user_service.py",
                        "symbol_name": "create_user",
                        "line_range": "1-80",
                    },
                    "reasoning": "The inspected target function body is available in the trace.",
                    "recommendation": "No change required from the inspected context.",
                }
            ],
            "checked_context": ["task_package", "graph_slice", "get_node_detail:create_user"],
            "remaining_questions": [],
            "message": "Function logic reviewed.",
            "requested_context": [],
            "downstream_result_ref": None,
        }


class _FakeWeakFinalLLMClient:
    def decide_next_action(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        trace: list[dict[str, object]],
        available_tools: list[str],
    ) -> dict[str, object]:
        return {
            "action": "final",
            "status": "completed",
            "context_sufficient": True,
            "requested_context": [],
            "downstream_result_ref": None,
        }


class _FakeWeakFinalWithWarningsLLMClient:
    def decide_next_action(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        trace: list[dict[str, object]],
        available_tools: list[str],
    ) -> dict[str, object]:
        return {
            "action": "final",
            "status": "blocked",
            "context_sufficient": False,
            "parser_warnings": ["missing summary", "missing findings"],
            "requested_context": [],
            "downstream_result_ref": None,
        }


class _FakeMissingToolArgsLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def decide_next_action(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        trace: list[dict[str, object]],
        available_tools: list[str],
    ) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return {
                "action": "call_tool",
                "tool_name": "get_node_detail",
                "tool_args": {},
                "reason": "Need target symbol details.",
            }
        if self.calls == 2:
            return {
                "action": "call_tool",
                "tool_name": "get_file_snippet",
                "tool_args": {"start_line": "bad", "end_line": 0},
                "reason": "Need target file snippet.",
            }
        if self.calls == 3:
            return {
                "action": "call_tool",
                "tool_name": "get_callees",
                "tool_args": {"depth": 20},
                "reason": "Need bounded downstream calls.",
            }
        return {
            "action": "final",
            "status": "completed",
            "context_sufficient": True,
            "summary": "Tool arguments were normalized from task runtime.",
            "findings": [{"title": "Argument normalization works", "severity": "info"}],
            "checked_context": ["get_node_detail", "get_file_snippet", "get_callees"],
            "remaining_questions": [],
            "requested_context": [],
            "downstream_result_ref": None,
        }


class _FakeMissingTargetFileLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def decide_next_action(
        self,
        *,
        task_package: dict[str, object],
        graph_slice: dict[str, object],
        related_context: dict[str, object],
        trace: list[dict[str, object]],
        available_tools: list[str],
    ) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return {
                "action": "call_tool",
                "tool_name": "get_related_context",
                "tool_args": {},
                "reason": "Try to expand module context.",
            }
        return {
            "action": "final",
            "status": "completed",
            "context_sufficient": True,
            "summary": "Missing target_file was surfaced as a tool error.",
            "findings": [{"title": "Tool error surfaced", "severity": "info"}],
            "checked_context": ["task_package", "graph_slice", "tool_error:get_related_context"],
            "remaining_questions": [],
            "requested_context": [],
            "downstream_result_ref": None,
        }
