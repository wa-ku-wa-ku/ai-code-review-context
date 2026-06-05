"""模型 API 调用和最小评审结果解析。"""

from dataclasses import dataclass, field
import json
import re
from typing import Any

import httpx

from review_agent.config import LLMApiConfig


@dataclass(frozen=True)
class ReviewResult:
    status: str
    context_sufficient: bool
    message: str
    requested_context: list[dict[str, Any]] = field(default_factory=list)
    downstream_result_ref: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMReviewClient:
    """调用系统环境配置的模型 API，返回可提交给 task-feedback 的结果。"""

    def __init__(
        self,
        config: LLMApiConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LLMReviewClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def review_task(
        self,
        *,
        task_package: dict[str, Any],
        graph_slice: dict[str, Any],
        related_context: dict[str, Any],
    ) -> ReviewResult:
        prompt = _build_prompt(task_package, graph_slice, related_context)
        if self._config.provider == "openai":
            payload = self._call_openai(prompt)
            content = _extract_openai_content(payload)
        elif self._config.provider == "anthropic":
            payload = self._call_anthropic(prompt)
            content = _extract_anthropic_content(payload)
        else:
            raise ValueError(f"unsupported provider: {self._config.provider}")
        parsed = _parse_review_content(content)
        return ReviewResult(raw_response=payload, **parsed)

    def _call_openai(self, prompt: str) -> dict[str, Any]:
        response = self._client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            json={
                "model": self._config.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        return response.json()

    def _call_anthropic(self, prompt: str) -> dict[str, Any]:
        response = self._client.post(
            "/messages",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "x-api-key": self._config.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self._config.model,
                "max_tokens": 1200,
                "temperature": 0,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        return response.json()


_SYSTEM_PROMPT = (
    "你是下游代码评审 agent。你只基于给定上下文做初步任务处理，"
    "不要请求完整仓库源码，不要伪造未读取的代码。输出必须是 JSON。"
)


def _build_prompt(
    task_package: dict[str, Any],
    graph_slice: dict[str, Any],
    related_context: dict[str, Any],
) -> str:
    # 控制输入边界：只传任务包、任务局部图和按需扩展上下文。
    payload = {
        "task_package": task_package,
        "task_graph_slice": graph_slice,
        "related_context": related_context,
        "required_output": {
            "status": "completed 或 blocked",
            "context_sufficient": "true 或 false",
            "message": "简短说明本轮处理结果或阻塞原因",
            "requested_context": "若 blocked，列出还需要的上下文请求；否则为空数组",
            "downstream_result_ref": "可选，更下游结果引用；没有则为 null",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_openai_content(payload: dict[str, Any]) -> str:
    return str(payload.get("choices", [{}])[0].get("message", {}).get("content", ""))


def _extract_anthropic_content(payload: dict[str, Any]) -> str:
    chunks = payload.get("content", [])
    texts = [str(item.get("text", "")) for item in chunks if isinstance(item, dict)]
    return "\n".join(text for text in texts if text)


def _parse_review_content(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        data = json.loads(match.group(0)) if match else {"message": content}

    status = str(data.get("status") or "completed")
    context_sufficient = bool(data.get("context_sufficient", status != "blocked"))
    requested_context = data.get("requested_context") or []
    if not isinstance(requested_context, list):
        requested_context = []
    return {
        "status": status,
        "context_sufficient": context_sufficient,
        "message": str(data.get("message") or "task processed"),
        "requested_context": requested_context,
        "downstream_result_ref": data.get("downstream_result_ref"),
    }
