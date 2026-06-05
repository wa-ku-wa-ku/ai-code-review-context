from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleScreeningResult:
    should_skip: bool = False
    skip_reason: str | None = None
    priority_boost: int = 0
    rule_flags: list[str] = field(default_factory=list)
    focus_areas: list[str] = field(default_factory=list)


@dataclass
class Finding:
    title: str
    description: str
    severity: str  # critical | high | medium | low | info
    file_path: str
    start_line: int = 0
    end_line: int = 0
    evidence: str = ""
    suggestion: str = ""


@dataclass
class LLMJudgmentResult:
    has_issue: bool = False
    confidence: float = 0.0
    findings: list[Finding] = field(default_factory=list)
    raw_response: str = ""
    parse_error: str | None = None


@dataclass
class GatheredContext:
    node_details: dict[str, dict] = field(default_factory=dict)
    file_snippets: dict[str, dict] = field(default_factory=dict)
    callee_chains: dict[str, list[dict]] = field(default_factory=dict)
    caller_chains: dict[str, list[dict]] = field(default_factory=dict)
    fetched_node_ids: set[str] = field(default_factory=set)
    fetched_file_ranges: set[str] = field(default_factory=set)

    def merge(self, other: GatheredContext) -> None:
        self.node_details.update(other.node_details)
        self.file_snippets.update(other.file_snippets)
        self.callee_chains.update(other.callee_chains)
        self.caller_chains.update(other.caller_chains)
        self.fetched_node_ids |= other.fetched_node_ids
        self.fetched_file_ranges |= other.fetched_file_ranges


@dataclass
class TaskAnalysisOutput:
    task_id: str
    status: str  # completed | blocked | skipped
    rule_result: RuleScreeningResult = field(default_factory=RuleScreeningResult)
    llm_result: LLMJudgmentResult | None = None
    context_sufficient: bool = True
    feedback_message: str = ""
    requested_context: list[dict[str, Any]] = field(default_factory=list)
