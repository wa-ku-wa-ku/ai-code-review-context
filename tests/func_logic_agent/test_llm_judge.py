from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from func_logic_agent.config import AgentConfig
from func_logic_agent.llm.llm_judge import (
    LLMJudge,
    _AnthropicBackend,
    _OpenAIBackend,
    _create_backend,
    _extract_json,
)
from func_logic_agent.models import GatheredContext, RuleScreeningResult


@pytest.fixture
def config():
    return AgentConfig(repo_id="test", llm_provider="anthropic", llm_model="claude-sonnet-4-20250514")


@pytest.fixture
def openai_config():
    return AgentConfig(
        repo_id="test",
        llm_provider="openai",
        llm_model="gpt-4o",
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com/v1",
    )


@pytest.fixture
def gathered():
    ctx = GatheredContext()
    ctx.node_details["n1"] = {
        "name": "login",
        "source": "def login(): pass",
    }
    return ctx


@pytest.fixture
def rule_result():
    return RuleScreeningResult(
        rule_flags=["high_risk_nodes_present"],
        focus_areas=["Input validation flow"],
    )


class TestCreateBackend:
    def test_anthropic_backend(self, config):
        backend = _create_backend(config)
        assert isinstance(backend, _AnthropicBackend)

    def test_openai_backend(self, openai_config):
        backend = _create_backend(openai_config)
        assert isinstance(backend, _OpenAIBackend)

    def test_unknown_provider_raises(self):
        cfg = AgentConfig(repo_id="test", llm_provider="unknown")
        with pytest.raises(ValueError, match="Unknown llm_provider"):
            _create_backend(cfg)

    def test_empty_defaults_to_anthropic(self):
        cfg = AgentConfig(repo_id="test", llm_provider="")
        backend = _create_backend(cfg)
        assert isinstance(backend, _AnthropicBackend)


class TestExtractJson:
    def test_direct_json(self):
        data = {"has_issue": False, "confidence": 0.9, "findings": []}
        result = _extract_json(json.dumps(data))
        assert result == data

    def test_json_in_code_block(self):
        data = {"has_issue": True, "confidence": 0.8, "findings": []}
        text = f"Here is the result:\n```json\n{json.dumps(data)}\n```"
        result = _extract_json(text)
        assert result == data

    def test_json_with_surrounding_text(self):
        data = {"has_issue": False, "confidence": 0.7, "findings": []}
        text = f"Some text before {json.dumps(data)} some text after"
        result = _extract_json(text)
        assert result == data

    def test_malformed_returns_none(self):
        result = _extract_json("this is not json at all")
        assert result is None


class TestParseResponse:
    def test_invalid_confidence_returns_parse_error(self, config):
        judge = LLMJudge(config)

        result = judge._parse_response(json.dumps({
            "has_issue": False,
            "confidence": "high",
            "findings": [],
        }))

        assert result.parse_error == "LLM response field 'confidence' must be numeric"
        assert result.confidence == 0.0

    def test_invalid_findings_shape_returns_parse_error(self, config):
        judge = LLMJudge(config)

        result = judge._parse_response(json.dumps({
            "has_issue": True,
            "confidence": 0.8,
            "findings": {"title": "not a list"},
        }))

        assert result.parse_error == "LLM response field 'findings' must be a list"
        assert result.findings == []


class TestAnthropicJudge:
    """Tests using the Anthropic backend (mocked at backend.chat level)."""

    @pytest.mark.asyncio
    async def test_judge_returns_structured_result(
        self, config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(
            return_value=json.dumps({
                "has_issue": False, "confidence": 0.85, "findings": [],
            })
        )

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is False
        assert result.confidence == 0.85
        assert result.findings == []
        assert result.parse_error is None

    @pytest.mark.asyncio
    async def test_judge_with_findings(
        self, config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(
            return_value=json.dumps({
                "has_issue": True,
                "confidence": 0.9,
                "findings": [
                    {
                        "title": "Missing null check",
                        "description": "authenticate may return None",
                        "severity": "high",
                        "file_path": "app/api/auth.py",
                        "start_line": 7,
                        "end_line": 8,
                        "evidence": "user = authenticate(...)",
                        "suggestion": "Add None check",
                    }
                ],
            })
        )

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is True
        assert len(result.findings) == 1
        assert result.findings[0].title == "Missing null check"
        assert result.findings[0].severity == "high"

    @pytest.mark.asyncio
    async def test_judge_handles_code_block_response(
        self, config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        json_str = json.dumps({"has_issue": False, "confidence": 0.7, "findings": []})
        judge = LLMJudge(config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(return_value=f"```json\n{json_str}\n```")

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is False
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_judge_handles_api_failure(
        self, config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(side_effect=Exception("API down"))

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is False
        assert result.parse_error is not None
        assert "API down" in result.parse_error

    @pytest.mark.asyncio
    async def test_judge_includes_focus_areas_in_prompt(
        self, config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        captured = {}

        async def capture_chat(**kwargs):
            captured["prompt"] = kwargs.get("user_prompt", "")
            return json.dumps({"has_issue": False, "confidence": 0.8, "findings": []})

        judge = LLMJudge(config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(side_effect=capture_chat)

        await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert "high_risk_nodes_present" in captured["prompt"]
        assert "Input validation flow" in captured["prompt"]


class TestOpenAIJudge:
    """Tests using the OpenAI backend (mocked at backend.chat level)."""

    @pytest.mark.asyncio
    async def test_openai_judge_works(
        self, openai_config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(openai_config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(
            return_value=json.dumps({
                "has_issue": False, "confidence": 0.8, "findings": [],
            })
        )

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is False
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_openai_judge_with_findings(
        self, openai_config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(openai_config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(
            return_value=json.dumps({
                "has_issue": True,
                "confidence": 0.85,
                "findings": [
                    {
                        "title": "Wrong return type",
                        "description": "Function returns str instead of dict",
                        "severity": "medium",
                        "file_path": "app/utils.py",
                        "start_line": 10,
                        "end_line": 15,
                        "evidence": "return 'ok' # should be {'status': 'ok'}",
                        "suggestion": "Return a dict",
                    }
                ],
            })
        )

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.has_issue is True
        assert result.findings[0].severity == "medium"

    @pytest.mark.asyncio
    async def test_openai_api_failure(
        self, openai_config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        judge = LLMJudge(openai_config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(side_effect=Exception("rate limited"))

        result = await judge.judge(
            sample_task_package, sample_graph_slice, gathered, rule_result
        )

        assert result.parse_error is not None
        assert "rate limited" in result.parse_error

    @pytest.mark.asyncio
    async def test_openai_followup(
        self, openai_config, sample_task_package, sample_graph_slice, gathered, rule_result
    ):
        from func_logic_agent.models import Finding, LLMJudgmentResult

        judge = LLMJudge(openai_config)
        judge._backend = MagicMock()
        judge._backend.chat = AsyncMock(
            return_value=json.dumps({
                "has_issue": True, "confidence": 0.9, "findings": [
                    {
                        "title": "Confirmed issue",
                        "description": "Null dereference",
                        "severity": "high",
                        "file_path": "app/api/auth.py",
                        "start_line": 7, "end_line": 8,
                        "evidence": "user = None; user.name",
                        "suggestion": "Add guard",
                    }
                ],
            })
        )

        prev = LLMJudgmentResult(
            has_issue=True,
            confidence=0.5,
            findings=[Finding(
                title="Suspected", description="maybe", severity="medium",
                file_path="app/api/auth.py",
            )],
        )

        result = await judge.judge_followup(
            previous_result=prev,
            requested_description="Need to see callers",
            new_context=gathered,
        )

        assert result.has_issue is True
        # Verify the followup prompt included previous findings
        call_args = judge._backend.chat.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1].get("user_prompt", "")
        assert "Suspected" in user_prompt


class TestConfigSwitching:
    """Verify config-driven provider switching works end to end."""

    def test_default_is_anthropic(self):
        cfg = AgentConfig(repo_id="test")
        assert cfg.llm_provider == "anthropic"
        backend = _create_backend(cfg)
        assert isinstance(backend, _AnthropicBackend)

    def test_openai_with_custom_base_url(self):
        cfg = AgentConfig(
            repo_id="test",
            llm_provider="openai",
            openai_api_key="sk-local",
            openai_base_url="http://localhost:8080/v1",
        )
        backend = _create_backend(cfg)
        assert isinstance(backend, _OpenAIBackend)

    def test_openai_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://local/v1")
        cfg = AgentConfig.from_env(repo_id="test")
        assert cfg.llm_provider == "openai"
        assert cfg.openai_api_key == "sk-env"
        assert cfg.openai_base_url == "http://local/v1"
