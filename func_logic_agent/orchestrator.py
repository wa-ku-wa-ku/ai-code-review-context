from __future__ import annotations

import asyncio
import logging
from typing import Any

from func_logic_agent.client.context_api_client import ContextAPIClient
from func_logic_agent.config import AgentConfig
from func_logic_agent.llm.llm_judge import LLMJudge
from func_logic_agent.models import (
    GatheredContext,
    TaskAnalysisOutput,
)
from func_logic_agent.rules.rule_engine import RuleEngine

logger = logging.getLogger(__name__)

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


class FuncLogicAgent:
    """Main orchestrator: fetch tasks, apply rules, judge with LLM, submit feedback."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = ContextAPIClient(
            config.context_api_base, config.request_timeout
        )
        self.rule_engine = RuleEngine(config)
        self.llm_judge = LLMJudge(config)

    async def run(
        self, repo_path: str, db_path: str | None = None
    ) -> list[TaskAnalysisOutput]:
        """Main entry point: index repo, process all function_logic tasks."""
        repo_id = self.config.repo_id
        if not repo_id:
            raise ValueError("config.repo_id must be set before calling run()")

        logger.info("Indexing repo %s at %s", repo_id, repo_path)
        index_result = await self.client.index_repo(repo_id, repo_path, db_path)
        tasks = index_result.get("review_tasks", [])

        # Filter for function_logic dimension
        fl_tasks = [t for t in tasks if t.get("review_dimension") == "function_logic"]
        fl_tasks.sort(key=lambda t: _PRIORITY_RANK.get(t.get("priority", ""), 9))

        if not fl_tasks:
            logger.info("No function_logic tasks found")
            return []

        fl_tasks = fl_tasks[: self.config.max_tasks_per_run]
        logger.info("Processing %d function_logic tasks", len(fl_tasks))

        results: list[TaskAnalysisOutput] = []
        for task in fl_tasks:
            try:
                output = await self._process_task(task)
                results.append(output)
            except Exception as exc:
                logger.error(
                    "Task %s failed: %s", task.get("task_id"), exc, exc_info=True
                )
                results.append(
                    TaskAnalysisOutput(
                        task_id=task.get("task_id", "?"),
                        status="blocked",
                        feedback_message=f"Agent error: {exc}",
                    )
                )

        return results

    async def _process_task(self, task: dict[str, Any]) -> TaskAnalysisOutput:
        """Process a single task through the full pipeline."""
        task_id = task["task_id"]
        repo_id = self.config.repo_id

        logger.info("Processing task %s", task_id)

        # 1. Get task package
        task_package = await self.client.get_task_package(task_id, repo_id)

        # 2. Get graph slice
        policy = task_package.get("context_policy", {})
        depth = policy.get("max_graph_depth", 2)
        graph_slice = await self.client.get_graph_slice(task_id, repo_id, depth=depth)

        # 3. Rule screening
        rule_result = self.rule_engine.screen(task_package, graph_slice)
        if rule_result.should_skip:
            logger.info("Skipping task %s: %s", task_id, rule_result.skip_reason)
            await self.client.submit_feedback(
                repo_id,
                task_id,
                agent=self.config.agent_name,
                status="skipped",
                context_sufficient=True,
                feedback_type="rule_skip",
                message=rule_result.skip_reason,
            )
            return TaskAnalysisOutput(
                task_id=task_id,
                status="skipped",
                rule_result=rule_result,
                feedback_message=rule_result.skip_reason or "",
            )

        # 4. Gather context
        gathered = await self._gather_context(task_package, graph_slice)

        # 5. LLM judgment
        llm_result = await self.llm_judge.judge(
            task_package=task_package,
            graph_slice=graph_slice,
            gathered_context=gathered,
            rule_result=rule_result,
        )

        if llm_result.parse_error:
            logger.warning(
                "LLM parse error for task %s: %s", task_id, llm_result.parse_error
            )

        # 6. Submit feedback and handle loop
        return await self._submit_and_loop(
            task_id, task_package, graph_slice, gathered, rule_result, llm_result
        )

    async def _gather_context(
        self,
        task_package: dict[str, Any],
        graph_slice: dict[str, Any],
        *,
        extra_requests: list[dict[str, Any]] | None = None,
    ) -> GatheredContext:
        """Gather detailed context from the API."""
        repo_id = self.config.repo_id
        task_id = task_package.get("task_id")
        ctx = GatheredContext()
        nodes = graph_slice.get("nodes", [])

        # Get node details for high-priority nodes
        high_priority = [n for n in nodes if (n.get("priority") or 0) >= 70]
        for node in high_priority:
            name = node.get("name")
            node_id = node.get("node_id")
            if not name or node_id in ctx.fetched_node_ids:
                continue
            detail = await self.client.get_node_detail(
                repo_id,
                symbol_name=name,
                task_id=task_id,
                review_dimension="function_logic",
            )
            if detail:
                ctx.node_details[node_id or name] = detail
                ctx.fetched_node_ids.add(node_id or name)

        # Get file snippet for the target
        target = task_package.get("target", {})
        file_path = target.get("file_path") if isinstance(target, dict) else None
        if file_path and file_path not in ctx.fetched_file_ranges:
            snippet = await self.client.get_file_snippet(
                repo_id,
                file_path,
                task_id=task_id,
                review_dimension="function_logic",
            )
            ctx.file_snippets[file_path] = snippet
            ctx.fetched_file_ranges.add(file_path)

        # Handle extra requests from feedback loop
        if extra_requests:
            await self._gather_extra_context(ctx, extra_requests, task_id)

        return ctx

    async def _gather_extra_context(
        self,
        ctx: GatheredContext,
        requests: list[dict[str, Any]],
        task_id: str | None,
    ) -> None:
        """Gather additional context based on feedback requests."""
        repo_id = self.config.repo_id

        for req in requests:
            req_type = req.get("type", "")

            if req_type == "node_detail":
                name = req.get("symbol_name") or req.get("name")
                if name:
                    detail = await self.client.get_node_detail(
                        repo_id,
                        symbol_name=name,
                        task_id=task_id,
                        review_dimension="function_logic",
                    )
                    if detail:
                        ctx.node_details[name] = detail
                        ctx.fetched_node_ids.add(name)

            elif req_type == "file_snippet":
                fp = req.get("file_path", "")
                start = req.get("start_line")
                end = req.get("end_line")
                key = f"{fp}:{start}:{end}"
                if key not in ctx.fetched_file_ranges:
                    snippet = await self.client.get_file_snippet(
                        repo_id, fp, start, end,
                        task_id=task_id,
                        review_dimension="function_logic",
                    )
                    ctx.file_snippets[key] = snippet
                    ctx.fetched_file_ranges.add(key)

            elif req_type == "callees":
                name = req.get("symbol_name")
                if name:
                    callees = await self.client.get_callees(
                        repo_id,
                        symbol_name=name,
                        depth=req.get("depth", 1),
                        task_id=task_id,
                        review_dimension="function_logic",
                    )
                    ctx.callee_chains[name] = callees

            elif req_type == "callers":
                name = req.get("symbol_name")
                if name:
                    callers = await self.client.get_callers(
                        repo_id,
                        symbol_name=name,
                        depth=req.get("depth", 1),
                        task_id=task_id,
                        review_dimension="function_logic",
                    )
                    ctx.caller_chains[name] = callers

    async def _submit_and_loop(
        self,
        task_id: str,
        task_package: dict[str, Any],
        graph_slice: dict[str, Any],
        gathered: GatheredContext,
        rule_result: Any,
        llm_result: Any,
    ) -> TaskAnalysisOutput:
        """Submit feedback and handle the context-request loop."""
        repo_id = self.config.repo_id
        retries = 0

        while True:
            needs_more = (
                llm_result.confidence < 0.5
                and not llm_result.parse_error
            )

            # Build feedback message
            if llm_result.parse_error:
                message = f"LLM parse error: {llm_result.parse_error}"
                status = "blocked"
            elif llm_result.has_issue:
                titles = [f.title for f in llm_result.findings]
                message = f"Found {len(llm_result.findings)} issue(s): {'; '.join(titles)}"
                status = "completed"
            else:
                message = "No functional logic issues found"
                status = "completed"

            requested_ctx = (
                self._build_requested_context(task_package, llm_result)
                if needs_more
                else []
            )
            if needs_more and not requested_ctx:
                needs_more = False

            response = await self.client.submit_feedback(
                repo_id,
                task_id,
                agent=self.config.agent_name,
                status=status,
                context_sufficient=not needs_more,
                feedback_type="function_logic_review",
                message=message,
                need_more_context=needs_more,
                requested_context=requested_ctx,
            )

            next_action = response.get("next_action", "continue_downstream")

            if (
                not needs_more
                or next_action != "provide_more_context"
                or retries >= self.config.max_context_retries
            ):
                break

            # Gather more context and re-judge
            retries += 1
            logger.info(
                "Feedback loop iteration %d for task %s", retries, task_id
            )
            extra_ctx = await self._gather_context(
                task_package, graph_slice, extra_requests=requested_ctx
            )
            gathered.merge(extra_ctx)

            llm_result = await self.llm_judge.judge_followup(
                previous_result=llm_result,
                requested_description=str(requested_ctx),
                new_context=extra_ctx,
            )

        return TaskAnalysisOutput(
            task_id=task_id,
            status=status if not llm_result.parse_error else "blocked",
            rule_result=rule_result,
            llm_result=llm_result,
            context_sufficient=not (llm_result.confidence < 0.5),
            feedback_message=message,
        )

    @staticmethod
    def _build_requested_context(
        task_package: dict[str, Any],
        llm_result: Any,
    ) -> list[dict[str, Any]]:
        """Build actionable context requests for a low-confidence judgment."""
        if llm_result.findings:
            first = llm_result.findings[0]
            if first.file_path:
                request: dict[str, Any] = {
                    "type": "file_snippet",
                    "file_path": first.file_path,
                    "reason": first.description,
                }
                if first.start_line > 0:
                    request["start_line"] = max(1, first.start_line - 20)
                if first.end_line > 0:
                    request["end_line"] = first.end_line + 20
                return [request]

        target = task_package.get("target", {})
        file_path = target.get("file_path") if isinstance(target, dict) else None
        if file_path:
            return [
                {
                    "type": "file_snippet",
                    "file_path": file_path,
                    "reason": "Low-confidence judgment needs target file context",
                }
            ]
        return []
