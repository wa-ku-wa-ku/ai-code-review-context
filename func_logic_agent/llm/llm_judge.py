from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from func_logic_agent.config import AgentConfig
from func_logic_agent.llm.prompts import (
    SYSTEM_PROMPT,
    build_followup_prompt,
    build_user_prompt,
)
from func_logic_agent.models import (
    Finding,
    GatheredContext,
    LLMJudgmentResult,
    RuleScreeningResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------

class _Backend(ABC):
    """LLM backend interface."""

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Send a single-turn chat and return the assistant text."""


class _AnthropicBackend(_Backend):
    def __init__(self) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic()

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


class _OpenAIBackend(_Backend):
    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        import openai
        kw: dict[str, Any] = {}
        if api_key:
            kw["api_key"] = api_key
        if base_url:
            kw["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kw)

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


def _create_backend(config: AgentConfig) -> _Backend:
    """Create the appropriate backend from config."""
    provider = config.llm_provider.lower()
    if provider == "openai":
        return _OpenAIBackend(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
    if provider in ("anthropic", ""):
        return _AnthropicBackend()
    raise ValueError(f"Unknown llm_provider: {config.llm_provider!r} (expected 'anthropic' or 'openai')")


# ---------------------------------------------------------------------------
# Main judge class
# ---------------------------------------------------------------------------

class LLMJudge:
    """Calls LLM for functional logic analysis and parses the response."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._backend = _create_backend(config)

    async def judge(
        self,
        task_package: dict[str, Any],
        graph_slice: dict[str, Any],
        gathered_context: GatheredContext,
        rule_result: RuleScreeningResult,
        previous_findings: list[Finding] | None = None,
    ) -> LLMJudgmentResult:
        """Send assembled context to LLM and return parsed result."""
        prev_dicts = None
        if previous_findings:
            prev_dicts = [
                {
                    "title": f.title,
                    "description": f.description,
                    "severity": f.severity,
                }
                for f in previous_findings
            ]

        context_dict = _gathered_to_dict(gathered_context)
        user_prompt = build_user_prompt(
            task_package=task_package,
            graph_slice=graph_slice,
            gathered_context=context_dict,
            rule_flags=rule_result.rule_flags,
            focus_areas=rule_result.focus_areas,
            previous_findings=prev_dicts,
        )

        return await self._call_and_parse(SYSTEM_PROMPT, user_prompt)

    async def judge_followup(
        self,
        previous_result: LLMJudgmentResult,
        requested_description: str,
        new_context: GatheredContext,
    ) -> LLMJudgmentResult:
        """Re-judge with additional context from the feedback loop."""
        new_ctx_dict = _gathered_to_dict(new_context)
        user_prompt = build_followup_prompt(
            requested_context_description=requested_description,
            new_context=new_ctx_dict,
        )

        prev_findings_dicts = [
            {
                "title": f.title,
                "description": f.description,
                "severity": f.severity,
                "evidence": f.evidence,
            }
            for f in previous_result.findings
        ]
        prefix = (
            f"Your previous analysis found these issues:\n"
            f"{json.dumps(prev_findings_dicts, indent=2)}\n\n"
        )

        return await self._call_and_parse(SYSTEM_PROMPT, prefix + user_prompt)

    async def _call_and_parse(
        self, system_prompt: str, user_prompt: str
    ) -> LLMJudgmentResult:
        """Call the backend and parse the response."""
        try:
            raw_text = await self._backend.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
            )
        except Exception as exc:
            logger.error("LLM API call failed: %s", exc)
            return LLMJudgmentResult(
                has_issue=False,
                confidence=0.0,
                raw_response="",
                parse_error=f"API error: {exc}",
            )

        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> LLMJudgmentResult:
        """Parse LLM response into a structured result."""
        parsed = _extract_json(raw_text)
        if parsed is None:
            return LLMJudgmentResult(
                has_issue=False,
                confidence=0.0,
                raw_response=raw_text,
                parse_error="Could not extract JSON from LLM response",
            )
        if not isinstance(parsed, dict):
            return LLMJudgmentResult(
                has_issue=False,
                confidence=0.0,
                raw_response=raw_text,
                parse_error="LLM response JSON must be an object",
            )

        findings = []
        raw_findings = parsed.get("findings", [])
        if not isinstance(raw_findings, list):
            return LLMJudgmentResult(
                has_issue=False,
                confidence=0.0,
                raw_response=raw_text,
                parse_error="LLM response field 'findings' must be a list",
            )

        for f in raw_findings:
            if not isinstance(f, dict):
                return LLMJudgmentResult(
                    has_issue=False,
                    confidence=0.0,
                    raw_response=raw_text,
                    parse_error="Each LLM finding must be an object",
                )
            findings.append(
                Finding(
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    severity=f.get("severity", "info"),
                    file_path=f.get("file_path", ""),
                    start_line=f.get("start_line", 0),
                    end_line=f.get("end_line", 0),
                    evidence=f.get("evidence", ""),
                    suggestion=f.get("suggestion", ""),
                )
            )

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            return LLMJudgmentResult(
                has_issue=False,
                confidence=0.0,
                raw_response=raw_text,
                parse_error="LLM response field 'confidence' must be numeric",
            )

        return LLMJudgmentResult(
            has_issue=parsed.get("has_issue", False),
            confidence=confidence,
            findings=findings,
            raw_response=raw_text,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any] | None:
    """Try multiple strategies to extract JSON from LLM response."""
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find first { and last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first : last + 1])
        except json.JSONDecodeError:
            pass

    return None


def _gathered_to_dict(ctx: GatheredContext) -> dict[str, Any]:
    """Convert GatheredContext to a plain dict for prompt building."""
    return {
        "node_details": ctx.node_details,
        "file_snippets": ctx.file_snippets,
        "callees": _flat_chain(ctx.callee_chains),
        "callers": _flat_chain(ctx.caller_chains),
        "target_detail": _extract_target(ctx.node_details),
    }


def _flat_chain(chains: dict[str, list[dict]]) -> list[dict]:
    """Flatten callee/caller chains into a deduplicated list."""
    seen: set[str] = set()
    result: list[dict] = []
    for items in chains.values():
        for item in items:
            key = item.get("node_id") or item.get("name", "")
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def _extract_target(node_details: dict[str, dict]) -> dict[str, Any] | None:
    """Pick the first node detail as the target detail."""
    for detail in node_details.values():
        return detail
    return None
