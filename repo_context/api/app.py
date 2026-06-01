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


@app.get("/demo/{repo_id}/nodes/{node_id}")
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
    p { line-height: 1.55; }
    main { display: grid; grid-template-columns: 360px 1fr 360px; gap: 16px; padding: 16px; }
    section { background: #ffffff; border: 1px solid #d8dde6; border-radius: 8px; padding: 16px; min-width: 0; }
    label { display: block; font-size: 13px; font-weight: 600; margin: 10px 0 5px; }
    input, button { box-sizing: border-box; width: 100%; padding: 9px 10px; border-radius: 6px; border: 1px solid #bcc4d0; font: inherit; }
    button { margin-top: 12px; border: 0; background: #2457c5; color: #fff; font-weight: 700; cursor: pointer; }
    button.secondary { background: #eef2f8; color: #172033; border: 1px solid #bcc4d0; }
    pre { overflow: auto; max-height: 420px; padding: 12px; background: #101828; color: #e7edf7; border-radius: 6px; font-size: 12px; }
    .task { border: 1px solid #d8dde6; border-radius: 6px; padding: 10px; margin-bottom: 8px; cursor: pointer; }
    .task:hover { background: #f3f6fb; }
    .pill { display: inline-block; padding: 2px 7px; border-radius: 999px; background: #edf2ff; color: #244aa5; font-size: 12px; margin-right: 4px; }
    .muted { color: #627089; font-size: 13px; }
    .grid { display: grid; gap: 12px; }
    @media (max-width: 1100px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>仓库上下文处理 Demo</h1>
    <p class="muted">输入本地代码目录，输出代码索引、仓库摘要、评审任务、推荐上下文和覆盖率报告。下游 Agent 通过这些接口拿上下文，不直接读取用户仓库。</p>
  </header>
  <main>
    <section>
      <h2>1. 输入本地目录</h2>
      <p class="muted">当前 demo 不上传代码。请填写后端机器可访问的 Python 仓库目录。</p>
      <label>repo_id</label>
      <input id="repoId" value="sample-repo" />
      <label>repo_path</label>
      <input id="repoPath" value="tests/fixtures/sample_repo" />
      <label>db_path 可选</label>
      <input id="dbPath" value=".demo_data/sample-repo.db" />
      <button onclick="buildIndex()">构建索引并生成输出</button>
      <button class="secondary" onclick="loadCoverage()">刷新覆盖率</button>
      <h2 style="margin-top: 20px;">任务列表</h2>
      <div id="tasks"></div>
    </section>

    <section>
      <h2>2. 输出内容</h2>
      <div class="grid">
        <div>
          <span class="pill">repo_summary</span>
          <span class="pill">review_tasks</span>
          <span class="pill">related_context</span>
          <span class="pill">coverage_report</span>
        </div>
        <pre id="output">{ "status": "等待构建索引" }</pre>
      </div>
    </section>

    <section>
      <h2>3. 给下游 Agent 的接口意图</h2>
      <p><strong>输入：</strong>用户本地 Python 仓库目录。</p>
      <p><strong>输出：</strong>SQLite 索引、任务卡、推荐上下文、源码片段和覆盖率报告。</p>
      <p><strong>Agent 接入方式：</strong></p>
      <pre>GET /demo/{repo_id}/tasks
GET /demo/{repo_id}/tasks/{task_id}/context
GET /demo/{repo_id}/nodes/{node_id}
GET /demo/{repo_id}/files/snippet
GET /demo/{repo_id}/coverage</pre>
      <p class="muted">Agent 应先按 task_id 获取推荐上下文，再按需读取节点详情或源码片段。读取行为会写入 context_usage，最后用于 coverage_report。</p>
    </section>
  </main>

  <script>
    let currentRepoId = "sample-repo";
    let currentTasks = [];

    function show(data) {
      document.getElementById("output").textContent = JSON.stringify(data, null, 2);
    }

    async function requestJson(url, options) {
      const response = await fetch(url, options);
      const text = await response.text();
      if (!response.ok) {
        throw new Error(text);
      }
      return JSON.parse(text);
    }

    async function buildIndex() {
      try {
        currentRepoId = document.getElementById("repoId").value.trim();
        const payload = {
          repo_id: currentRepoId,
          repo_path: document.getElementById("repoPath").value.trim(),
          db_path: document.getElementById("dbPath").value.trim() || null
        };
        const data = await requestJson("/demo/index", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        currentTasks = data.review_tasks || [];
        renderTasks();
        show(data);
      } catch (error) {
        show({ error: String(error) });
      }
    }

    function renderTasks() {
      const box = document.getElementById("tasks");
      box.innerHTML = "";
      currentTasks.forEach(task => {
        const item = document.createElement("div");
        item.className = "task";
        item.onclick = () => loadTaskContext(task.task_id);
        item.innerHTML = `<strong>${task.task_id}</strong><br><span class="muted">${task.task_type} · ${task.target}</span>`;
        box.appendChild(item);
      });
    }

    async function loadTaskContext(taskId) {
      try {
        const data = await requestJson(`/demo/${currentRepoId}/tasks/${encodeURIComponent(taskId)}/context`);
        show(data);
      } catch (error) {
        show({ error: String(error) });
      }
    }

    async function loadCoverage() {
      try {
        const repoId = document.getElementById("repoId").value.trim();
        const data = await requestJson(`/demo/${repoId}/coverage`);
        show(data);
      } catch (error) {
        show({ error: String(error) });
      }
    }
  </script>
</body>
</html>
"""
