"""下游 agent 的环境配置读取。"""

from dataclasses import dataclass
import os


class LLMConfigError(RuntimeError):
    """LLM API 配置缺失或不完整。"""


@dataclass(frozen=True)
class ContextApiConfig:
    base_url: str
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class LLMApiConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class DownstreamAgentConfig:
    agent_name: str
    context_api: ContextApiConfig
    llm_api: LLMApiConfig

    @classmethod
    def from_env(cls) -> "DownstreamAgentConfig":
        """从系统环境读取上下文服务和模型服务配置。"""
        provider = _read_provider()
        return cls(
            agent_name=os.getenv("REVIEW_AGENT_NAME", "security-review-agent"),
            context_api=ContextApiConfig(
                base_url=os.getenv("CONTEXT_API_BASE_URL", "http://127.0.0.1:8000"),
                timeout_seconds=float(os.getenv("CONTEXT_API_TIMEOUT", "30")),
            ),
            llm_api=_read_llm_config(provider),
        )


def _read_provider() -> str:
    provider = os.getenv("REVIEW_AGENT_PROVIDER")
    if provider:
        return provider.lower()
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise LLMConfigError(
        "缺少模型 API 配置：请设置 REVIEW_AGENT_PROVIDER，并提供对应的 API key 和模型名。"
    )


def _read_llm_config(provider: str) -> LLMApiConfig:
    if provider == "openai":
        api_key_name = "OPENAI_API_KEY"
        model_name = "OPENAI_MODEL"
        default_base_url = "https://api.openai.com/v1"
    elif provider == "anthropic":
        api_key_name = "ANTHROPIC_API_KEY"
        model_name = "ANTHROPIC_MODEL"
        default_base_url = "https://api.anthropic.com/v1"
    else:
        raise LLMConfigError(f"不支持的 REVIEW_AGENT_PROVIDER: {provider}")

    api_key = os.getenv(api_key_name)
    model = os.getenv("REVIEW_AGENT_MODEL") or os.getenv(model_name)
    if not api_key:
        raise LLMConfigError(f"缺少 {api_key_name}")
    if not model:
        raise LLMConfigError(f"缺少 REVIEW_AGENT_MODEL 或 {model_name}")

    base_url = (
        os.getenv("REVIEW_AGENT_BASE_URL")
        or os.getenv(f"{provider.upper()}_BASE_URL")
        or default_base_url
    )
    return LLMApiConfig(
        provider=provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=float(os.getenv("REVIEW_AGENT_TIMEOUT", "60")),
    )
