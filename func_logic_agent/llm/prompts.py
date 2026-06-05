"""Prompt templates for the functional logic review LLM."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are a functional logic code reviewer. Your job is to analyze Python code \
for functional logic issues ONLY.

Functional logic issues include:
- Incorrect control flow (missing branches, unreachable code, wrong condition logic)
- Incomplete error handling (exceptions swallowed, missing try/except for fallible ops)
- State mutation bugs (shared mutable state, race conditions in async code)
- Return value contract violations (function returns wrong type/None unexpectedly)
- Off-by-one or boundary errors in loops and slicing
- Dead code or unused return values that indicate forgotten logic
- Incorrect data transformation (wrong aggregation, lost fields, type coercion bugs)
- Missing default/edge case handling

You must NOT flag:
- Security vulnerabilities (that's a different review dimension)
- Code style issues (naming, formatting, documentation)
- Performance concerns unless they cause incorrect results

Be conservative: only flag issues with clear evidence from the provided code. \
If no functional logic issues are found, say so honestly.

Output format: respond with a single JSON object matching this schema:
{
  "has_issue": boolean,
  "confidence": float (0.0 to 1.0),
  "findings": [
    {
      "title": "short issue title",
      "description": "detailed explanation",
      "severity": "critical|high|medium|low|info",
      "file_path": "path/to/file.py",
      "start_line": int,
      "end_line": int,
      "evidence": "quote the relevant code or describe the specific logic",
      "suggestion": "how to fix it"
    }
  ]
}

Do NOT include any text outside the JSON object.\
"""


def build_user_prompt(
    task_package: dict,
    graph_slice: dict,
    gathered_context: dict,
    rule_flags: list[str],
    focus_areas: list[str],
    previous_findings: list[dict] | None = None,
) -> str:
    """Build the user prompt from gathered context."""
    sections: list[str] = []

    # -- Task metadata -------------------------------------------------------
    target = task_package.get("target", {})
    if isinstance(target, dict):
        file_path = target.get("file_path", "")
        symbols = target.get("symbols", [])
    else:
        file_path = str(target)
        symbols = []

    sections.append(
        f"## Task\n"
        f"- Task ID: {task_package.get('task_id', '?')}\n"
        f"- Task type: {task_package.get('task_type', '?')}\n"
        f"- Target file: {file_path}\n"
        f"- Target symbols: {', '.join(symbols) if symbols else 'N/A'}\n"
        f"- Priority: {task_package.get('priority', '?')}\n"
        f"- Focus points: {', '.join(task_package.get('focus_points', []))}\n"
        f"- Rule flags: {', '.join(rule_flags) if rule_flags else 'none'}\n"
        f"- Focus areas from rules: {', '.join(focus_areas) if focus_areas else 'none'}"
    )

    # -- Graph summary -------------------------------------------------------
    nodes = graph_slice.get("nodes", [])
    edges = graph_slice.get("edges", [])
    boundary = graph_slice.get("boundary_nodes", [])
    graph_lines = [
        f"- Nodes: {len(nodes)}, Edges: {len(edges)}, Boundary nodes: {len(boundary)}"
    ]
    top_nodes = sorted(nodes, key=lambda n: n.get("priority", 0), reverse=True)[:8]
    for n in top_nodes:
        graph_lines.append(
            f"  - {n.get('name', '?')} | relation={n.get('relation_to_target', '?')} "
            f"| priority={n.get('priority', '?')} | risk={n.get('risk_score', 0)} "
            f"| reason={n.get('reason', '')}"
        )
    sections.append("## Call Graph Summary\n" + "\n".join(graph_lines))

    # -- Previous findings (feedback loop) -----------------------------------
    if previous_findings:
        findings_text = "\n".join(
            f"- [{f.get('severity', '?')}] {f.get('title', '?')}: {f.get('description', '')}"
            for f in previous_findings
        )
        sections.append(f"## Previous Analysis\n{findings_text}")

    # -- Target source code --------------------------------------------------
    target_detail = gathered_context.get("target_detail")
    if target_detail:
        source = target_detail.get("source", "")
        if source:
            sections.append(f"## Target Code\n```\n{source}\n```")

    # -- Node details (callee + caller source) -------------------------------
    node_details = gathered_context.get("node_details", {})
    if node_details:
        blocks = []
        for nid, detail in list(node_details.items())[:10]:
            name = detail.get("name", nid)
            source = detail.get("source", "")
            if source:
                blocks.append(f"### {name}\n```\n{source}\n```")
        if blocks:
            sections.append("## Related Code\n" + "\n\n".join(blocks))

    # -- Callee / caller chains ----------------------------------------------
    callees = gathered_context.get("callees", [])
    if callees:
        callee_lines = []
        for c in callees[:10]:
            callee_lines.append(
                f"- {c.get('name', '?')} (depth={c.get('depth', '?')}, "
                f"file={c.get('file_path', '?')})"
            )
        sections.append("## Callees\n" + "\n".join(callee_lines))

    callers = gathered_context.get("callers", [])
    if callers:
        caller_lines = []
        for c in callers[:10]:
            caller_lines.append(
                f"- {c.get('name', '?')} (depth={c.get('depth', '?')}, "
                f"file={c.get('file_path', '?')})"
            )
        sections.append("## Callers\n" + "\n".join(caller_lines))

    # -- Analysis instruction ------------------------------------------------
    sections.append(
        "## Analysis Instructions\n"
        "Based on the above context, identify any functional logic issues. "
        "Focus on the areas flagged by the rule engine. "
        "Return your findings as the specified JSON object."
    )

    return "\n\n".join(sections)


def build_followup_prompt(
    requested_context_description: str,
    new_context: dict,
) -> str:
    """Build a follow-up prompt when more context was requested."""
    sections = [
        "## Additional Context Requested",
        requested_context_description,
        "## New Context Provided",
    ]

    new_details = new_context.get("node_details", {})
    if new_details:
        for nid, detail in list(new_details.items())[:5]:
            name = detail.get("name", nid)
            source = detail.get("source", "")
            if source:
                sections.append(f"### {name}\n```\n{source}\n```")

    new_snippets = new_context.get("file_snippets", {})
    if new_snippets:
        for key, snippet in list(new_snippets.items())[:3]:
            content = snippet.get("content", snippet.get("source", ""))
            if content:
                sections.append(f"### {key}\n```\n{content}\n```")

    sections.append(
        "## Updated Analysis\n"
        "Re-evaluate considering the new information above. "
        "Return your updated findings as the specified JSON object."
    )

    return "\n\n".join(sections)
