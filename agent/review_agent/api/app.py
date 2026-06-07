"""功能逻辑 agent demo 服务。

这个 FastAPI 应用属于 agent 模块，只负责运行下游 agent 并展示 trace。
它不会实现 context 模块的索引、任务生成或评分规则；这些仍然通过
CONTEXT_API_BASE_URL 指向的 context 服务完成。
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from review_agent.core import FunctionLogicAgent


app = FastAPI(title="Function Logic Agent Demo")


class AgentRunRequest(BaseModel):
    repo_id: str
    task_id: str
    graph_depth: int = 2
    max_steps: int = Field(default=6, ge=1, le=12)


@app.get("/", response_class=HTMLResponse)
def agent_demo_page() -> str:
    return _AGENT_DEMO_HTML


@app.post("/agent/function-logic/run")
def run_function_logic_agent(request: AgentRunRequest) -> dict[str, Any]:
    """运行一次功能逻辑 agent，并返回完整 trace。"""

    try:
        agent = FunctionLogicAgent.from_env()
        return agent.run_task_trace(
            repo_id=request.repo_id,
            task_id=request.task_id,
            graph_depth=request.graph_depth,
            max_steps=request.max_steps,
        )
    except Exception as exc:  # noqa: BLE001 - demo 需要把运行错误展示给前端
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_AGENT_DEMO_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Function Logic Agent Trace</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --border: #d9e1ec;
      --soft: #eef3f8;
      --brand: #2563eb;
      --ok: #167647;
      --warn: #b54708;
      --danger: #b42318;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); }
    header {
      height: 72px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 14px 18px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
    }
    h1 { margin: 0; font-size: 20px; }
    h2 { margin: 0; font-size: 15px; }
    h3 { margin: 0 0 8px; font-size: 14px; }
    main {
      display: grid;
      grid-template-columns: 340px minmax(520px, 1fr) 420px;
      gap: 12px;
      padding: 12px;
      height: calc(100vh - 72px);
    }
    .panel {
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .head {
      padding: 11px 12px;
      border-bottom: 1px solid var(--border);
      background: #fbfcfe;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .body { padding: 12px; overflow: auto; min-height: 0; }
    label { display: block; margin: 10px 0 5px; color: var(--muted); font-size: 12px; font-weight: 800; }
    input {
      width: 100%;
      height: 36px;
      border: 1px solid #c7d0dd;
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
      font-size: 13px;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--brand);
      color: #fff;
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }
    button.secondary { background: var(--soft); color: var(--text); border: 1px solid #c7d0dd; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .muted { color: var(--muted); }
    .small { font-size: 12px; line-height: 1.45; }
    .box {
      border: 1px solid var(--border);
      border-radius: 7px;
      background: #fff;
      padding: 10px;
      margin-bottom: 10px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 20px;
      border-radius: 999px;
      padding: 2px 7px;
      background: var(--soft);
      color: #344054;
      font-size: 12px;
      font-weight: 800;
    }
    .pill.ai { background: #eef4ff; color: var(--brand); }
    .pill.tool { background: #ecfdf3; color: var(--ok); }
    .pill.final { background: #fff7e6; color: var(--warn); }
    .event {
      border-left: 3px solid var(--border);
      padding: 0 0 12px 12px;
      margin-left: 6px;
    }
    .event.ai_request, .event.ai_response { border-left-color: var(--brand); }
    .event.tool_call, .event.tool_result { border-left-color: var(--ok); }
    .event.final_result, .event.task_feedback { border-left-color: var(--warn); }
    .event-title { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    pre {
      margin: 0;
      max-height: 380px;
      overflow: auto;
      padding: 10px;
      border-radius: 7px;
      background: #101828;
      color: #e6edf7;
      font-size: 12px;
      line-height: 1.5;
    }
    .empty {
      padding: 22px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed #b7c1cf;
      border-radius: 7px;
      background: #fbfcfe;
    }
    .kv { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 7px 10px; font-size: 13px; }
    .kv div:nth-child(odd) { color: var(--muted); font-weight: 800; }
    @media (max-width: 1180px) {
      header { height: auto; align-items: flex-start; flex-direction: column; }
      main { grid-template-columns: 1fr; height: auto; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Function Logic Agent Trace</h1>
      <div class="muted small">展示 AI 决策、工具调用、工具结果、最终结论和 task-feedback 的完整信息流。</div>
    </div>
    <div id="status" class="muted small">等待运行。</div>
  </header>

  <main>
    <aside class="panel">
      <div class="head"><h2>Run</h2></div>
      <div class="body">
        <div class="box">
          <label for="repoId">repo_id</label>
          <input id="repoId" value="sample-repo" />
          <label for="taskId">task_id</label>
          <input id="taskId" value="task_module_app_services" />
          <div class="row">
            <div>
              <label for="graphDepth">graph_depth</label>
              <input id="graphDepth" value="2" />
            </div>
            <div>
              <label for="maxSteps">max_steps</label>
              <input id="maxSteps" value="6" />
            </div>
          </div>
          <button style="width:100%;margin-top:12px" onclick="runAgent()">Run Agent</button>
        </div>
        <div class="box small muted">
          当前 demo 是功能逻辑 agent。context 索引需要先由 context 服务完成；agent 只通过 CONTEXT_API_BASE_URL 调用公开接口。
        </div>
        <div id="summary" class="box"><div class="empty">暂无运行结果。</div></div>
      </div>
    </aside>

    <section class="panel">
      <div class="head">
        <h2>Trace Timeline</h2>
        <button class="secondary" onclick="copyRaw()">Copy Raw</button>
      </div>
      <div id="timeline" class="body"><div class="empty">点击 Run Agent 后显示每轮 AI 和工具交互。</div></div>
    </section>

    <aside class="panel">
      <div class="head"><h2>Raw JSON</h2></div>
      <div id="raw" class="body"><pre>{}</pre></div>
    </aside>
  </main>

  <script>
    let lastRun = null;

    async function runAgent() {
      const body = {
        repo_id: value("repoId"),
        task_id: value("taskId"),
        graph_depth: Number(value("graphDepth") || 2),
        max_steps: Number(value("maxSteps") || 6)
      };
      setStatus("Running function logic agent...");
      try {
        const response = await fetch("/agent/function-logic/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        const text = await response.text();
        const data = parseMaybeJson(text);
        if (!response.ok) throw new Error(JSON.stringify(data));
        lastRun = data;
        renderSummary(data);
        renderTrace(data.trace || []);
        renderRaw(data);
        setStatus(`Done: ${data.final_result?.status || "-"}`);
      } catch (error) {
        renderRaw({ error: String(error), request: body });
        setStatus(`Failed: ${String(error)}`);
      }
    }

    function renderSummary(data) {
      document.getElementById("summary").innerHTML = `
        <h3>Final Result</h3>
        <div class="kv">
          <div>agent</div><div>${html(data.agent || "-")}</div>
          <div>repo_id</div><div>${html(data.repo_id || "-")}</div>
          <div>task_id</div><div>${html(data.task_id || "-")}</div>
          <div>dimension</div><div>${html(data.review_dimension || "-")}</div>
          <div>status</div><div>${html(data.final_result?.status || "-")}</div>
          <div>sufficient</div><div>${html(data.final_result?.context_sufficient ?? "-")}</div>
          <div>findings</div><div>${html((data.final_result?.findings || []).length)}</div>
          <div>warnings</div><div>${html((data.final_result?.parser_warnings || []).join(", ") || "-")}</div>
        </div>
        <div class="box small" style="margin:10px 0 0">${html(data.final_result?.summary || data.final_result?.message || "-")}</div>
      `;
    }

    function renderTrace(events) {
      if (!events.length) {
        document.getElementById("timeline").innerHTML = `<div class="empty">trace 为空。</div>`;
        return;
      }
      document.getElementById("timeline").innerHTML = events.map((event, index) => `
        <div class="event ${html(event.type)}">
          <div class="event-title">
            <span class="pill ${eventClass(event.type)}">${html(event.type)}</span>
            <span class="muted small">#${index + 1}</span>
          </div>
          ${renderEventBody(event)}
        </div>
      `).join("");
    }

    function renderEventBody(event) {
      const payload = event.payload || {};
      if (event.type === "ai_request") {
        return `<div class="small muted">AI 输入摘要：available_tools、trace_event_count、step</div><pre>${json(payload)}</pre>`;
      }
      if (event.type === "ai_response") {
        return `<div class="small">AI 输出：${html(payload.action || "-")} ${payload.tool_name ? "→ " + html(payload.tool_name) : ""}</div><pre>${json(payload)}</pre>`;
      }
      if (event.type === "tool_call") {
        return `<div class="small">工具调用：${html(payload.tool_name || "-")}</div><div class="small muted">${html(payload.reason || "")}</div><pre>${json(payload.tool_args || {})}</pre>`;
      }
      if (event.type === "tool_result") {
        return `<div class="small">工具结果：${html(payload.tool_name || payload.name || "-")}</div><pre>${json(payload.result ?? payload)}</pre>`;
      }
      if (event.type === "final_result") {
        return `<div class="small">最终结论</div><pre>${json(payload)}</pre>`;
      }
      if (event.type === "task_feedback") {
        return `<div class="small">已回传 task-feedback</div><pre>${json(payload.feedback || {})}</pre>`;
      }
      return `<pre>${json(payload)}</pre>`;
    }

    function eventClass(type) {
      if (type.startsWith("ai_")) return "ai";
      if (type.startsWith("tool_")) return "tool";
      if (type === "final_result" || type === "task_feedback") return "final";
      return "";
    }

    function renderRaw(data) {
      document.getElementById("raw").innerHTML = `<pre>${json(data)}</pre>`;
    }

    async function copyRaw() {
      await navigator.clipboard.writeText(JSON.stringify(lastRun || {}, null, 2));
      setStatus("Raw JSON copied.");
    }

    function value(id) {
      return document.getElementById(id).value.trim();
    }

    function parseMaybeJson(text) {
      try { return JSON.parse(text); } catch { return text; }
    }

    function json(value) {
      return html(JSON.stringify(value ?? {}, null, 2));
    }

    function html(value) {
      return String(value ?? "-")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function setStatus(text) {
      document.getElementById("status").textContent = text;
    }
  </script>
</body>
</html>
"""
