"""模型 API 调用与评审结果解析。

这个 client 的职责很窄：把已经准备好的任务包和上下文材料发给模型，
再把模型返回的 JSON 解析成 ReviewResult。它不直接调用上下文服务，
也不直接决定还要读哪些代码；这些由 agent orchestration 层负责。
"""

from dataclasses import dataclass, field
import json
import re
from typing import Any

import httpx

from review_agent.config import LLMApiConfig


@dataclass(frozen=True)
class ReviewResult:
    """一次任务评审的标准输出。

    这些字段会被 BasicReviewAgent / FunctionLogicAgent 转成
    POST /context/task-feedback 的请求体，所以这里保持和反馈接口兼容。
    """

    status: str
    context_sufficient: bool
    message: str
    requested_context: list[dict[str, Any]] = field(default_factory=list)
    downstream_result_ref: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMReviewClient:
    """调用系统环境配置的模型 API。

    DeepSeek 的接口按 OpenAI compatible chat completions 调用，因此和
    OpenAI 分支共用同一套请求和响应解析逻辑。Anthropic 分支保留给后续
    如果要切 Claude 系列模型时使用。
    """

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
        tool_results: list[dict[str, Any]] | None = None,
    ) -> ReviewResult:
        """让模型基于当前上下文完成一次任务判断。

        tool_results 是 FunctionLogicAgent 额外调用 file-snippet、node-detail、
        callers、callees 等工具后的结果集合。这里把它作为上下文材料传给模型，
        不让模型自己直接访问外部接口，从而保证工具调用仍由 agent 代码控制。
        """

        prompt = _build_prompt(
            task_package=task_package,
            graph_slice=graph_slice,
            related_context=related_context,
            tool_results=tool_results or [],
        )
        if self._config.provider in {"openai", "deepseek"}:
            payload = self._call_openai_compatible(prompt)
            content = _extract_openai_content(payload)
        elif self._config.provider == "anthropic":
            payload = self._call_anthropic(prompt)
            content = _extract_anthropic_content(payload)
        else:
            raise ValueError(f"unsupported provider: {self._config.provider}")
        parsed = _parse_review_content(content)
        return ReviewResult(raw_response=payload, **parsed)

    def decide_next_action(
        self,
        *,
        task_package: dict[str, Any],
        graph_slice: dict[str, Any],
        related_context: dict[str, Any],
        trace: list[dict[str, Any]],
        available_tools: list[str],
    ) -> dict[str, Any]:
        """让模型决定下一步是调用工具还是给出最终结论。

        返回 JSON 约定：
        - call_tool: {"action": "call_tool", "tool_name": "...", "tool_args": {...}, "reason": "..."}
        - final: {"action": "final", "status": "completed|blocked", "context_sufficient": true|false, ...}
        """

        prompt = _build_action_prompt(
            task_package=task_package,
            graph_slice=graph_slice,
            related_context=related_context,
            trace=trace,
            available_tools=available_tools,
        )
        if self._config.provider in {"openai", "deepseek"}:
            payload = self._call_openai_compatible(prompt)
            content = _extract_openai_content(payload)
        elif self._config.provider == "anthropic":
            payload = self._call_anthropic(prompt)
            content = _extract_anthropic_content(payload)
        else:
            raise ValueError(f"unsupported provider: {self._config.provider}")
        decision = _parse_decision_content(content)
        decision["raw_response"] = payload
        return decision

    def _call_openai_compatible(self, prompt: str) -> dict[str, Any]:
        """调用 OpenAI compatible 的 /chat/completions 接口。"""

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
    "你是一个功能逻辑代码评审 agent。你只能基于用户提供的 task package、"
    "task-local graph slice 和上下文工具返回内容进行判断。不要假设未读取的代码，"
    "不要要求完整仓库源码。输出必须是 JSON 对象。"
)


def _build_prompt(
    *,
    task_package: dict[str, Any],
    graph_slice: dict[str, Any],
    related_context: dict[str, Any],
    tool_results: list[dict[str, Any]],
) -> str:
    """构造模型输入。

    这里故意只传结构化上下文，不传 agent 内部对象。这样模型看到的内容
    和下游接口文档一致，也方便以后把同一套输入交给不同供应商模型。
    """

    payload = {
        "task_package": task_package,
        "task_graph_slice": graph_slice,
        "related_context": related_context,
        "additional_context_tool_results": tool_results,
        "required_output": {
            "status": "completed 或 blocked",
            "context_sufficient": "true 或 false",
            "message": "简短说明本轮处理结果、功能逻辑风险或阻塞原因",
            "requested_context": "如果 blocked，列出仍需要的上下文请求；否则为空数组",
            "downstream_result_ref": "可选，下游结果引用；没有则为 null",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_action_prompt(
    *,
    task_package: dict[str, Any],
    graph_slice: dict[str, Any],
    related_context: dict[str, Any],
    trace: list[dict[str, Any]],
    available_tools: list[str],
) -> str:
    """构造“下一步动作”提示词。

    这里把历史 trace 一并传入，让模型知道已经调用过哪些工具、拿到了什么结果。
    agent 仍然负责真正执行工具，模型只负责选择下一步动作和说明原因。
    """

    payload = {
        "role": "function_logic_agent_controller",
        "task_package": task_package,
        "task_graph_slice": graph_slice,
        "related_context": related_context,
        "trace_so_far": trace,
        "available_tools": available_tools,
        "allowed_tool_names": [
            "get_related_context",
            "get_file_snippet",
            "get_node_detail",
            "get_callees",
            "get_callers",
        ],
        "required_output": {
            "call_tool": {
                "action": "call_tool",
                "tool_name": "one allowed tool name",
                "tool_args": "JSON object arguments",
                "reason": "why this tool is needed",
            },
            "final": {
                "action": "final",
                "status": "completed or blocked",
                "context_sufficient": "true or false",
                "message": "final functional-logic conclusion or blocking reason",
                "requested_context": "array, empty unless blocked",
                "downstream_result_ref": "optional string or null",
            },
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
    """把模型输出解析成 task-feedback 可用字段。

    模型偶尔会在 JSON 前后带说明文字，所以这里先尝试直接 json.loads，
    失败后再从文本里截取第一个 JSON object。仍然失败时，把原文放进
    message，避免 agent 因模型格式问题中断整条任务流程。
    """

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


def _parse_decision_content(content: str) -> dict[str, Any]:
    """解析模型的下一步动作。

    如果模型输出不符合约定，则保守地转成 final/blocked，避免无限循环。
    """

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        data = json.loads(match.group(0)) if match else {"message": content}

    if not isinstance(data, dict):
        data = {"message": str(data)}
    action = str(data.get("action") or "final")
    if action == "call_tool":
        tool_args = data.get("tool_args") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}
        return {
            "action": "call_tool",
            "tool_name": str(data.get("tool_name") or ""),
            "tool_args": tool_args,
            "reason": str(data.get("reason") or "model requested context tool"),
        }
    requested_context = data.get("requested_context") or []
    if not isinstance(requested_context, list):
        requested_context = []
    status = str(data.get("status") or "completed")
    return {
        "action": "final",
        "status": status,
        "context_sufficient": bool(data.get("context_sufficient", status != "blocked")),
        "message": str(data.get("message") or "task processed"),
        "requested_context": requested_context,
        "downstream_result_ref": data.get("downstream_result_ref"),
    }
