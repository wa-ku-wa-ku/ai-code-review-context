# AI Code Review Context

这是一个面向“仓库级 AI 代码评审”的上下文处理模块。它不直接判断漏洞，也不生成最终评审结论；它负责把一个 Python 仓库解析成可查询的上下文索引，并给下游 review agent 提供受控、可追踪、可逐步扩展的代码上下文。

## 能力边界

本模块负责：

- 读取本地 Python 仓库或安全解压 zip 包。
- 扫描并过滤有效文件。
- 使用 Python 标准库 `ast` 抽取 module、class、function、method、route、import、decorator 和基础调用关系。
- 构建 SQLite 上下文索引。
- 生成仓库摘要和规则化 review task package。
- 提供上下文查询 API 和 service 工具。
- 记录下游 agent 实际读取过的文件、符号和图关系，并生成覆盖率报告。

本模块不负责：

- 不做漏洞判断。
- 不生成最终评审报告。
- 不做多 agent 调度。
- 不把完整仓库源码一次性塞给 agent。
- 不暴露完整仓库调用图，只暴露 task-local graph slice。

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

当前根目录依赖包括：

```text
fastapi
httpx
pytest
```

`httpx` 是 FastAPI / Starlette `TestClient` 的测试依赖。不要为了当前测试随意改成 `httpx2`。

## 快速开始

使用项目自带的 sample repo 构建索引：

```python
from pathlib import Path

from repo_context.index.index_builder import build_index
from repo_context.service.context_service import ContextService
from repo_context.service.coverage_service import CoverageService
from repo_context.task.review_task_generator import ReviewTaskGenerator

repo_id = "sample-repo"
repo_path = Path("tests/fixtures/sample_repo")
db_path = Path("demo_context.db")

build_index(repo_id=repo_id, repo_path=repo_path, db_path=db_path)

context_service = ContextService(
    repo_id=repo_id,
    repo_root=repo_path,
    db_path=db_path,
)
task_generator = ReviewTaskGenerator(context_service)
coverage_service = CoverageService(context_service, task_generator)

plan = task_generator.generate()
first_task = plan.review_tasks[0].to_dict()
coverage = coverage_service.get_coverage_report()

print(first_task)
print(coverage)
```

## Review Task Package

下游 agent 不应该一次性拿到完整仓库源码。任务生成器会为每个任务提供一个有限的 task package：

```json
{
  "task_id": "task_route_post_login",
  "task_type": "entrypoint_review",
  "review_dimension": "security",
  "target": {
    "type": "file",
    "file_path": "app/api/auth.py",
    "symbols": ["login"]
  },
  "tags": ["api_entry", "auth"],
  "focus_points": ["输入校验", "身份认证", "异常处理"],
  "initial_context": {
    "file_snippets": [],
    "related_symbols": [],
    "call_graph_slice": {
      "graph_scope": "local",
      "center": "app.api.auth.login",
      "depth": 2,
      "nodes": [],
      "edges": []
    },
    "requirement_refs": []
  },
  "available_tools": [
    "get_file_snippet",
    "get_node_detail",
    "get_callers",
    "get_callees",
    "trace_call_chain",
    "search_symbol",
    "get_related_context"
  ],
  "context_policy": {
    "max_depth": 2,
    "max_snippet_lines": 120,
    "max_files": 5,
    "allow_expand": true
  }
}
```

重点约束：

- `initial_context` 只放少量起始上下文。
- `call_graph_slice` 是任务局部图，不是完整仓库 graph。
- agent 需要更多上下文时，再调用 `available_tools` 中的接口逐步扩展。
- 每次上下文读取都会尽量写入 `context_usage`，用于覆盖率统计。

## ContextService 工具

常用 service 方法：

```python
matches = context_service.search_symbol("login")

node = context_service.get_node_detail(
    symbol_name="login",
    task_id="task_route_post_login",
    review_dimension="security",
)

snippet = context_service.get_file_snippet(
    file_path="app/api/auth.py",
    start_line=1,
    end_line=40,
    task_id="task_route_post_login",
    review_dimension="security",
)

callees = context_service.get_callees(
    symbol_name="login",
    depth=1,
    task_id="task_route_post_login",
    review_dimension="security",
)

related = context_service.get_related_context(
    {
        "task_id": "task_route_post_login",
        "target": {
            "type": "file",
            "file_path": "app/api/auth.py",
            "symbols": ["login"]
        },
        "review_dimension": "security",
        "tags": ["api_entry", "auth"]
    }
)
```

`get_file_snippet()` 会拒绝仓库外路径，例如 `../../secret.txt`。

## FastAPI API

启动服务：

```powershell
uvicorn repo_context.api.app:app --reload
```

先索引一个本地仓库：

```http
POST /context/index
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "repo_path": "tests/fixtures/sample_repo",
  "db_path": ".demo_data/sample-repo.db"
}
```

上下文查询接口：

```text
GET  /context/file-snippet
GET  /context/node-detail
GET  /context/callees
GET  /context/callers
POST /context/related-context
GET  /context/task-package/{task_id}
```

示例：

```http
GET /context/file-snippet?repo_id=sample-repo&file_path=app/api/auth.py&start_line=1&end_line=40
```

```http
GET /context/node-detail?repo_id=sample-repo&symbol_name=login
```

```http
POST /context/related-context
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "target_file": "app/api/auth.py",
  "review_dimension": "security",
  "tags": ["api_entry", "auth"],
  "max_depth": 1,
  "max_files": 2
}
```

Demo 页面和兼容 demo API 仍然可用：

```text
GET  /
POST /demo/index
GET  /demo/{repo_id}/tasks
GET  /demo/{repo_id}/tasks/{task_id}/context
GET  /demo/{repo_id}/coverage
```

## Context Usage 和覆盖率

`context_usage` 会记录下游 agent 实际读过什么：

- `task_id`
- `agent` / `review_dimension`
- `tool_name`
- `target_type`
- `target_name`
- `node_id`
- `file_path`
- `start_line`
- `end_line`
- `lines_returned`
- `created_at`

覆盖率报告：

```python
coverage = coverage_service.get_coverage_report()
```

可用于判断：

- 哪些文件被实际读取过。
- 哪些符号被实际查看过。
- 哪些任务已经触发过上下文访问。
- 哪些文件还需要生成 `uncovered_file_review` 补充任务。

## 测试

运行完整测试：

```powershell
python -m pytest -q
```

编译检查：

```powershell
python -m compileall -q repo_context
```

当前 pytest 配置会跳过 `tests/fixtures` 下的第三方示例仓库内部测试。那些文件是被本项目扫描和解析的输入样本，不属于本项目自身测试集。

## 前端接入建议

推荐前端流程：

1. 让用户选择本地仓库路径或 zip 上传后的服务端路径。
2. 调用 `/context/index` 构建索引。
3. 展示 `repo_summary` 和 `review_tasks`。
4. 点击任务卡片后展示完整 task package。
5. 默认展示 `initial_context`，不要展示完整仓库源码。
6. 当用户或 agent 需要更多上下文时，调用 `/context/file-snippet`、`/context/node-detail`、`/context/callees`、`/context/related-context`。
7. 展示 coverage report，让用户知道哪些文件和符号已被实际读取。

任务卡片建议展示：

- 任务类型和 review dimension。
- 目标文件和目标符号。
- tags 和 priority。
- focus points。
- initial context 摘要。
- graph slice 节点数和边数。
- “继续扩展上下文”的操作入口。
