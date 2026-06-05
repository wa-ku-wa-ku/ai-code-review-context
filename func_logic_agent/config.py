from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields


@dataclass
class AgentConfig:
    # Context API
    context_api_base: str = "http://127.0.0.1:8000"
    repo_id: str = ""

    # LLM — provider: "anthropic" or "openai"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1
    # OpenAI-compatible settings (used when llm_provider="openai")
    openai_api_key: str = ""
    openai_base_url: str = ""

    # Rule engine thresholds
    graph_node_count_high: int = 15
    graph_node_count_low: int = 3
    risk_score_threshold: int = 40
    io_keywords: list[str] = field(
        default_factory=lambda: [
            "query", "execute", "read", "write", "request", "fetch",
            "send", "receive", "open", "connect", "download", "upload",
        ]
    )
    error_handling_keywords: list[str] = field(
        default_factory=lambda: [
            "try", "except", "catch", "handle", "error", "fallback",
            "retry", "raise", "throw",
        ]
    )

    # Orchestrator
    max_context_retries: int = 3
    max_tasks_per_run: int = 50
    request_timeout: float = 30.0
    agent_name: str = "func-logic-agent"

    @classmethod
    def from_env(cls, **overrides) -> AgentConfig:
        """Load config from environment variables with overrides."""
        kw: dict = {}
        env_map = {
            "CONTEXT_API_BASE": ("context_api_base", str),
            "REPO_ID": ("repo_id", str),
            "LLM_PROVIDER": ("llm_provider", str),
            "LLM_MODEL": ("llm_model", str),
            "LLM_MAX_TOKENS": ("llm_max_tokens", int),
            "LLM_TEMPERATURE": ("llm_temperature", float),
            "OPENAI_API_KEY": ("openai_api_key", str),
            "OPENAI_BASE_URL": ("openai_base_url", str),
            "MAX_CONTEXT_RETRIES": ("max_context_retries", int),
            "REQUEST_TIMEOUT": ("request_timeout", float),
            "AGENT_NAME": ("agent_name", str),
        }
        for env_key, (attr, cast) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                kw[attr] = cast(val)
        kw.update(overrides)
        return cls(**kw)

    @classmethod
    def from_json(cls, path: str, **overrides) -> AgentConfig:
        """Load config from a JSON file with overrides."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.update(overrides)
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})
