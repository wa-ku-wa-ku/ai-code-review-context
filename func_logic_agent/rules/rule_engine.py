from __future__ import annotations

import logging
from typing import Any

from func_logic_agent.config import AgentConfig
from func_logic_agent.models import RuleScreeningResult

logger = logging.getLogger(__name__)


class RuleEngine:
    """Deterministic rule-based pre-screening for function_logic tasks."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def screen(
        self, task_package: dict[str, Any], graph_slice: dict[str, Any]
    ) -> RuleScreeningResult:
        """Apply all rules and return a screening result."""
        result = RuleScreeningResult()
        nodes: list[dict] = graph_slice.get("nodes", [])
        boundary_nodes: list[dict] = graph_slice.get("boundary_nodes", [])
        task_type = task_package.get("task_type", "")
        priority = task_package.get("priority", "")

        self._r1_graph_complexity(nodes, result)
        self._r2_high_risk_nodes(nodes, result)
        self._r3_deep_call_chain(nodes, result)
        self._r4_boundary_risk(boundary_nodes, result)
        self._r5_error_path(nodes, result)
        self._r6_task_type_focus(task_type, result)
        self._r7_skip_trivial(task_type, priority, nodes, result)

        return result

    # -- Individual rules ----------------------------------------------------

    def _r1_graph_complexity(
        self, nodes: list[dict], result: RuleScreeningResult
    ) -> None:
        count = len(nodes)
        if count > self.config.graph_node_count_high:
            result.rule_flags.append("complex_graph")
            result.focus_areas.append(
                f"Graph has {count} nodes — focus on the highest-priority targets first"
            )
        elif count < self.config.graph_node_count_low:
            result.rule_flags.append("trivial_graph")

    def _r2_high_risk_nodes(
        self, nodes: list[dict], result: RuleScreeningResult
    ) -> None:
        threshold = self.config.risk_score_threshold
        risky = [
            n for n in nodes if (n.get("risk_score") or 0) >= threshold
        ]
        if risky:
            result.rule_flags.append("high_risk_nodes_present")
            result.priority_boost += 10 * len(risky)
            for n in risky:
                name = n.get("name", "?")
                reason = n.get("reason", "")
                result.focus_areas.append(
                    f"High-risk node: {name} (risk_score={n.get('risk_score')}) — {reason}"
                )

    def _r3_deep_call_chain(
        self, nodes: list[dict], result: RuleScreeningResult
    ) -> None:
        for n in nodes:
            if (
                n.get("relation_to_target") == "indirect"
                and (n.get("depth") or 0) >= 2
            ):
                result.rule_flags.append("deep_call_chain")
                result.focus_areas.append(
                    "Deep call chain detected — verify contracts between delegation layers"
                )
                return

    def _r4_boundary_risk(
        self, boundary_nodes: list[dict], result: RuleScreeningResult
    ) -> None:
        risky_boundary = [
            n for n in boundary_nodes if (n.get("risk_score") or 0) > 0
        ]
        if risky_boundary:
            result.rule_flags.append("risk_at_boundary")
            result.priority_boost += 5 * len(risky_boundary)
            names = ", ".join(n.get("name", "?") for n in risky_boundary[:3])
            result.focus_areas.append(
                f"Risky boundary nodes outside scope: {names}"
            )

    def _r5_error_path(
        self, nodes: list[dict], result: RuleScreeningResult
    ) -> None:
        io_keywords = set(self.config.io_keywords)
        error_keywords = set(self.config.error_handling_keywords)

        has_io = False
        has_error_handling = False

        for n in nodes:
            name_lower = (n.get("name") or "").lower()
            reason_lower = (n.get("reason") or "").lower()
            combined = name_lower + " " + reason_lower

            if any(kw in combined for kw in io_keywords):
                has_io = True
            if any(kw in combined for kw in error_keywords):
                has_error_handling = True

        if has_io and not has_error_handling:
            result.rule_flags.append("potential_missing_error_handling")
            result.focus_areas.append(
                "IO operations detected without clear error handling — check exception paths"
            )

    def _r6_task_type_focus(
        self, task_type: str, result: RuleScreeningResult
    ) -> None:
        if task_type == "entrypoint_review":
            result.focus_areas.extend([
                "Input validation flow",
                "Response correctness",
                "Error propagation to caller",
            ])
        elif task_type == "module_review":
            result.focus_areas.extend([
                "Internal state consistency",
                "Return value contracts",
            ])
        elif task_type == "config_review":
            result.focus_areas.extend([
                "Configuration value correctness",
                "Default value handling",
            ])

    def _r7_skip_trivial(
        self,
        task_type: str,
        priority: str,
        nodes: list[dict],
        result: RuleScreeningResult,
    ) -> None:
        if (
            task_type == "file_review"
            and priority == "low"
            and len(nodes) < self.config.graph_node_count_low
        ):
            result.should_skip = True
            result.skip_reason = (
                "Low-priority file with trivial structure; rule-only pass sufficient"
            )
