from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from repo_context.index.index_builder import build_index
from repo_context.service.context_service import ContextService
from repo_context.service.coverage_service import CoverageService
from repo_context.task.review_task_generator import ReviewTaskGenerator


app = FastAPI(title="AI Code Review Context")

_DEMO_SESSIONS: dict[str, dict[str, Any]] = {}


@app.get("/health")
def health() -> dict[str, str]:
    """最小健康检查接口，用于验证阶段 0 API 骨架可启动。"""
    return {"status": "ok"}


class DemoIndexRequest(BaseModel):
    repo_id: str
    repo_path: str
    db_path: str | None = None


@app.get("/", response_class=HTMLResponse)
def demo_page() -> str:
    return _DEMO_HTML


@app.post("/demo/index")
def demo_index(request: DemoIndexRequest) -> dict[str, Any]:
    repo_path = Path(request.repo_path).expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"repo_path is not a directory: {repo_path}")

    db_path = (
        Path(request.db_path).expanduser().resolve()
        if request.db_path
        else Path.cwd() / ".demo_data" / f"{request.repo_id}.db"
    )
    result = build_index(request.repo_id, repo_path, db_path)
    service = _create_services(request.repo_id, repo_path, db_path)
    plan = service["task_generator"].generate()
    coverage = service["coverage_service"].get_coverage_report()
    _DEMO_SESSIONS[request.repo_id] = {
        "repo_root": str(repo_path),
        "db_path": str(db_path),
    }

    return {
        "index_result": result.__dict__,
        "repo_summary": plan.repo_summary.to_dict(),
        "review_tasks": [task.to_dict() for task in plan.review_tasks],
        "task_coverage_report": plan.coverage_report,
        "usage_coverage_report": coverage,
    }


@app.get("/demo/{repo_id}/summary")
def demo_summary(repo_id: str) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    plan = service["task_generator"].generate()
    return {
        "repo_summary": plan.repo_summary.to_dict(),
        "task_coverage_report": plan.coverage_report,
    }


@app.get("/demo/{repo_id}/tasks")
def demo_tasks(repo_id: str) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    plan = service["task_generator"].generate()
    return {"review_tasks": [task.to_dict() for task in plan.review_tasks]}


@app.get("/demo/{repo_id}/tasks/{task_id}/context")
def demo_task_context(repo_id: str, task_id: str) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    return service["task_generator"].get_related_context(task_id)


@app.get("/demo/{repo_id}/nodes/{node_id:path}")
def demo_node_detail(repo_id: str, node_id: str, task_id: str | None = None) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    detail = service["context_service"].get_node_detail(
        node_id,
        include_source=True,
        task_id=task_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="node not found")
    return detail


@app.get("/demo/{repo_id}/files/snippet")
def demo_file_snippet(
    repo_id: str,
    file_path: str,
    start_line: int,
    end_line: int,
    task_id: str | None = None,
) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    return service["context_service"].get_file_snippet(
        file_path,
        start_line,
        end_line,
        task_id=task_id,
    )


@app.get("/demo/{repo_id}/coverage")
def demo_coverage(repo_id: str) -> dict[str, Any]:
    service = _load_demo_services(repo_id)
    return {
        "usage_coverage_report": service["coverage_service"].get_coverage_report(),
        "uncovered_file_reviews": [
            task.to_dict()
            for task in service["coverage_service"].generate_uncovered_file_reviews()
        ],
    }


def _load_demo_services(repo_id: str) -> dict[str, Any]:
    session = _DEMO_SESSIONS.get(repo_id)
    if session is None:
        raise HTTPException(status_code=404, detail="repo_id has not been indexed in this process")
    return _create_services(repo_id, Path(session["repo_root"]), Path(session["db_path"]))


def _create_services(repo_id: str, repo_root: Path, db_path: Path) -> dict[str, Any]:
    context_service = ContextService(repo_id=repo_id, repo_root=repo_root, db_path=db_path)
    task_generator = ReviewTaskGenerator(context_service)
    coverage_service = CoverageService(context_service, task_generator)
    return {
        "context_service": context_service,
        "task_generator": task_generator,
        "coverage_service": coverage_service,
    }


_DEMO_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Code Review Context Demo</title>
  <style>
    :root { color-scheme: light; font-family: "Segoe UI", Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #172033; }
    header { padding: 20px 28px; background: #ffffff; border-bottom: 1px solid #d8dde6; }
    h1 { margin: 0 0 6px; font-size: 24px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    h3 { margin: 0 0 8px; font-size: 15px; }
    p { line-height: 1.55; margin: 8px 0; }
    main { display: grid; grid-template-columns: 340px 1fr 380px; gap: 16px; padding: 16px; }
    section { background: #ffffff; border: 1px solid #d8dde6; border-radius: 8px; padding: 16px; min-width: 0; }
    label { display: block; font-size: 13px; font-weight: 600; margin: 10px 0 5px; }
    input, button { box-sizing: border-box; width: 100%; padding: 9px 10px; border-radius: 6px; border: 1px solid #bcc4d0; font: inherit; }
    button { margin-top: 12px; border: 0; background: #2457c5; color: #fff; font-weight: 700; cursor: pointer; }
    button.secondary { background: #eef2f8; color: #172033; border: 1px solid #bcc4d0; }
    button.inline { width: auto; margin: 4px 6px 4px 0; padding: 6px 9px; font-size: 12px; }
    pre { overflow: auto; max-height: 360px; padding: 12px; background: #101828; color: #e7edf7; border-radius: 6px; font-size: 12px; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .card { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; }
    .metric { font-size: 24px; font-weight: 800; margin: 4px 0; }
    .task { border: 1px solid #d8dde6; border-radius: 6px; padding: 10px; margin-bottom: 8px; cursor: pointer; background: #fff; }
    .task:hover { background: #f3f6fb; }
    .task.active { border-color: #2457c5; background: #eef4ff; }
    .pill { display: inline-block; padding: 2px 7px; border-radius: 999px; background: #edf2ff; color: #244aa5; font-size: 12px; margin-right: 4px; }
    .priority-high { background: #fff0f0; color: #b42318; }
    .priority-medium { background: #fff7e6; color: #9a5b00; }
    .priority-low { background: #eff8f0; color: #1f7a3a; }
    .muted { color: #627089; font-size: 13px; }
    .grid { display: grid; gap: 12px; }
    .empty { padding: 24px; color: #627089; text-align: center; border: 1px dashed #bcc4d0; border-radius: 8px; }
    .list { margin: 8px 0 0; padding-left: 18px; }
    details { border: 1px solid #d8dde6; border-radius: 8px; padding: 10px; background: #fff; }
    summary { cursor: pointer; font-weight: 700; }
    @media (max-width: 1100px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>仓库上下文处理 Demo</h1>
    <p class="muted">输入本地代码目录，生成给下游 Agent 使用的代码上下文索引、评审任务、推荐上下文和覆盖率数据。</p>
  </header>
  <main>
    <section>
      <h2>分析项目</h2>
      <p class="muted">当前 demo 不上传代码，只读取后端机器可访问的本地目录。</p>
      <label>项目名称</label>
      <input id="projectName" value="sample repo" />
      <label>代码目录</label>
      <input id="repoPath" value="tests/fixtures/sample_repo" />
      <button onclick="buildIndex()">开始分析</button>
      <button class="secondary" onclick="loadCoverage()">刷新实际覆盖率</button>
      <p id="status" class="muted">等待开始。</p>
      <h2 style="margin-top: 20px;">任务列表</h2>
      <div id="tasks"></div>
    </section>

    <section>
      <h2>分析结果</h2>
      <div class="grid">
        <div id="summaryCards" class="cards"></div>
        <div id="coverageCards" class="cards"></div>
        <div id="taskDetail" class="empty">点击“开始分析”后，这里会展示仓库摘要、任务卡片和推荐上下文。</div>
        <details>
          <summary>查看原始 JSON</summary>
          <pre id="output">{ "status": "等待构建索引" }</pre>
        </details>
      </div>
    </section>

    <section>
      <h2>给下游 Agent 的说明</h2>
      <p><strong>输入：</strong>本地 Python 仓库目录。</p>
      <p><strong>输出：</strong>仓库摘要、任务卡、推荐节点/文件、源码片段、覆盖率报告。</p>
      <p><strong>建议接入顺序：</strong></p>
      <ol class="list">
        <li>读取任务列表。</li>
        <li>按 task_id 获取推荐上下文。</li>
        <li>按需读取节点详情或源码片段。</li>
        <li>用 coverage_report 判断还有哪些代码没覆盖。</li>
      </ol>
      <pre>GET /demo/{repo_id}/tasks
GET /demo/{repo_id}/tasks/{task_id}/context
GET /demo/{repo_id}/nodes/{node_id}
GET /demo/{repo_id}/files/snippet
GET /demo/{repo_id}/coverage</pre>
      <p class="muted">注意：任务覆盖率表示“任务计划覆盖了什么”；实际覆盖率表示“Agent 工具真的访问过什么”。刚构建完时实际覆盖率可能为 0，点击节点或源码片段后会更新。</p>
    </section>
  </main>

  <script>
    let currentRepoId = "";
    let currentTasks = [];
    let lastPayload = null;
    let activeTaskId = null;

    function show(data) {
      document.getElementById("output").textContent = JSON.stringify(data, null, 2);
    }

    function setStatus(text) {
      document.getElementById("status").textContent = text;
    }

    async function requestJson(url, options) {
      const response = await fetch(url, options);
      const text = await response.text();
      if (!response.ok) {
        throw new Error(text);
      }
      return JSON.parse(text);
    }

    function slug(value) {
      return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "demo-repo";
    }

    async function buildIndex() {
      try {
        setStatus("正在读取目录、扫描文件、解析代码并构建索引...");
        currentRepoId = slug(document.getElementById("projectName").value);
        const payload = {
          repo_id: currentRepoId,
          repo_path: document.getElementById("repoPath").value.trim(),
          db_path: `.demo_data/${currentRepoId}.db`
        };
        const data = await requestJson("/demo/index", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        lastPayload = data;
        currentTasks = data.review_tasks || [];
        activeTaskId = null;
        renderTasks();
        renderSummary(data.repo_summary);
        renderCoverage(data.task_coverage_report, data.usage_coverage_report);
        renderOverview(data);
        show(data);
        setStatus("分析完成。点击左侧任务查看推荐上下文。");
      } catch (error) {
        setStatus("分析失败。");
        show({ error: String(error) });
      }
    }

    function renderTasks() {
      const box = document.getElementById("tasks");
      box.innerHTML = "";
      if (!currentTasks.length) {
        box.innerHTML = `<div class="empty">暂无任务。</div>`;
        return;
      }
      currentTasks.forEach(task => {
        const item = document.createElement("div");
        item.className = `task ${task.task_id === activeTaskId ? "active" : ""}`;
        item.onclick = () => loadTaskContext(task.task_id);
        item.innerHTML = `
          <strong>${humanTaskType(task.task_type)}：${escapeHtml(task.target)}</strong><br>
          <span class="pill priority-${task.priority}">${task.priority}</span>
          <span class="muted">${task.task_id}</span>
        `;
        box.appendChild(item);
      });
    }

    function renderSummary(summary) {
      document.getElementById("summaryCards").innerHTML = `
        ${metricCard("框架", summary.framework || "unknown", "识别到的 Web 框架")}
        ${metricCard("Python 文件", summary.python_files, "参与分析的 Python 文件数")}
        ${metricCard("API 入口", summary.entrypoints.length, "路由入口数量")}
        ${metricCard("配置文件", summary.config_files.length, "需要关注的配置文件")}
      `;
    }

    function renderCoverage(taskCoverage, usageCoverage) {
      const taskRatio = percent(taskCoverage.coverage_ratio);
      const fileRatio = percent(usageCoverage.file_coverage);
      const nodeRatio = percent(usageCoverage.node_coverage);
      const taskDone = percent(usageCoverage.task_completion_rate);
      document.getElementById("coverageCards").innerHTML = `
        ${metricCard("任务计划覆盖", taskRatio, `未覆盖文件：${taskCoverage.uncovered_python_files.length}`)}
        ${metricCard("实际文件覆盖", fileRatio, `已访问文件：${usageCoverage.covered_files.length}`)}
        ${metricCard("实际节点覆盖", nodeRatio, `已访问节点：${usageCoverage.covered_nodes.length}`)}
        ${metricCard("任务完成率", taskDone, `已触达任务：${usageCoverage.completed_task_ids.length}`)}
      `;
    }

    function renderOverview(data) {
      const summary = data.repo_summary;
      document.getElementById("taskDetail").innerHTML = `
        <div class="card">
          <h3>这个仓库分析出了什么？</h3>
          <p>系统已生成 <strong>${data.review_tasks.length}</strong> 张评审任务卡。下游 Agent 可以按任务逐个获取推荐上下文。</p>
          <p><strong>入口点：</strong>${summary.entrypoints.map(item => escapeHtml(item.method_path)).join("，") || "未发现"}</p>
          <p><strong>测试文件：</strong>${summary.test_files.length} 个；<strong>配置文件：</strong>${summary.config_files.join("，") || "无"}</p>
        </div>
      `;
    }

    async function loadTaskContext(taskId) {
      try {
        activeTaskId = taskId;
        renderTasks();
        const data = await requestJson(`/demo/${currentRepoId}/tasks/${encodeURIComponent(taskId)}/context`);
        const task = currentTasks.find(item => item.task_id === taskId);
        renderTaskDetail(task, data);
        show(data);
      } catch (error) {
        show({ error: String(error) });
      }
    }

    function renderTaskDetail(task, context) {
      if (!task) return;
      const nodes = context.recommended_nodes || [];
      const files = context.related_files || [];
      document.getElementById("taskDetail").innerHTML = `
        <div class="card">
          <h3>${humanTaskType(task.task_type)}：${escapeHtml(task.target)}</h3>
          <p><span class="pill priority-${task.priority}">${task.priority}</span><span class="muted">${task.task_id}</span></p>
          <p><strong>为什么看它：</strong>${escapeHtml(context.reason || task.reason || "该任务由规则生成。")}</p>
          <p><strong>关注点：</strong></p>
          <ul class="list">${task.review_focus.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          <p><strong>推荐节点：</strong></p>
          <div>${nodes.length ? nodes.map(node => `<button class="inline secondary" onclick="loadNode('${encodeURIComponent(node.node_id)}', '${task.task_id}')">${escapeHtml(node.qualified_name)}</button>`).join("") : "<span class='muted'>无推荐节点</span>"}</div>
          <p><strong>相关文件：</strong></p>
          <div>${files.map(file => `<button class="inline secondary" onclick="loadSnippet('${encodeURIComponent(file)}', '${task.task_id}')">${escapeHtml(file)}</button>`).join("")}</div>
        </div>
      `;
    }

    async function loadNode(encodedNodeId, taskId) {
      try {
        const data = await requestJson(`/demo/${currentRepoId}/nodes/${encodedNodeId}?task_id=${encodeURIComponent(taskId)}`);
        show(data);
        await loadCoverage();
      } catch (error) {
        show({ error: String(error) });
      }
    }

    async function loadSnippet(encodedFile, taskId) {
      try {
        const data = await requestJson(`/demo/${currentRepoId}/files/snippet?file_path=${encodedFile}&start_line=1&end_line=40&task_id=${encodeURIComponent(taskId)}`);
        show(data);
        await loadCoverage();
      } catch (error) {
        show({ error: String(error) });
      }
    }

    async function loadCoverage() {
      try {
        const repoId = currentRepoId || slug(document.getElementById("projectName").value);
        const data = await requestJson(`/demo/${repoId}/coverage`);
        if (lastPayload) {
          renderCoverage(lastPayload.task_coverage_report, data.usage_coverage_report);
        }
        show(data);
      } catch (error) {
        show({ error: String(error) });
      }
    }

    function metricCard(title, value, hint) {
      return `<div class="card"><div class="muted">${title}</div><div class="metric">${value}</div><div class="muted">${escapeHtml(String(hint || ""))}</div></div>`;
    }

    function percent(value) {
      return `${Math.round((value || 0) * 100)}%`;
    }

    function humanTaskType(type) {
      const names = {
        entrypoint_review: "入口评审",
        config_review: "配置评审",
        module_review: "模块评审",
        file_review: "文件评审",
        uncovered_file_review: "未覆盖文件补审"
      };
      return names[type] || type;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }
  </script>
</body>
</html>
"""
