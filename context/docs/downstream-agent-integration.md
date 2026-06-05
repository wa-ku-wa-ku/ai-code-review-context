# 下游工程师接入说明

本文面向接入本模块的下游 review agent / 工程服务。目标是说明：如何构建仓库上下文索引、如何领取任务包、如何按需查询上下文、如何记录上下文使用情况，以及如何回传评审过程中的状态。

接口参数和返回字段详见 `context/docs/context-api-reference.md`。Postman 导入文件见 `context/docs/api/postman_collection.json`。

## 接入流程

推荐流程：

1. 调用 `/context/index` 为目标仓库构建索引。
2. 从返回值中读取 `review_tasks`。
3. 下游 agent 按任务逐个处理，不要一次性读取完整仓库源码。
4. 对每个任务，调用 `/context/task-package/{task_id}` 获取完整任务包。
5. 先消费轻量 `initial_context`，确认目标、关注点和 `suggested_next_tool`。
6. 优先调用 `/context/tasks/{task_id}/graph-slice` 获取 task-local graph slice。
7. 如果上下文不足，再调用 `available_tools` 对应接口扩展上下文。
8. 每次上下文查询会自动写入 `context_usage`。
9. 处理完成后，下游系统可读取 `/demo/{repo_id}/coverage` 查看实际覆盖率。

## 1. 构建索引

请求：

```http
POST /context/index
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "repo_path": "tests/fixtures/sample_repo",
  "db_path": ".demo_data/sample-repo.db"
}
```

字段说明：

- `repo_id`：本次仓库分析的唯一标识。
- `repo_path`：服务端本机可访问的 Python 仓库目录。
- `db_path`：SQLite 索引文件路径。

返回重点字段：

- `repo_summary`：仓库摘要。
- `review_tasks`：下游 agent 要处理的任务列表。
- `task_coverage_report`：任务生成阶段的规划覆盖率。
- `usage_coverage_report`：实际上下文读取覆盖率。

## 2. 领取任务

索引完成后，从 `review_tasks` 中读取任务。每个任务都包含：

```json
{
  "task_id": "task_route_post_login",
  "task_type": "entrypoint_review",
  "review_dimension": "security",
  "priority": "high",
  "target": {
    "type": "file",
    "file_path": "app/api/auth.py",
    "symbols": ["POST /login", "login"]
  },
  "tags": ["api_entry", "auth"],
  "focus_points": ["输入校验", "身份认证", "异常处理"],
  "context_policy": {
    "max_depth": 2,
    "max_snippet_lines": 120,
    "max_files": 6,
    "allow_expand": true,
    "allow_task_graph_slice": true,
    "allow_full_graph": false,
    "prefer_graph_slice_first": true,
    "max_graph_depth": 2
  }
}
```

下游调度建议：

- 优先处理 `priority = high` 的任务。
- 同一个任务只分配给一个 review agent。
- 不要把所有任务同时强行分配给所有 agent。
- 不要绕过任务包直接读取完整仓库源码。

## 3. 获取完整任务包

请求：

```http
GET /context/task-package/{task_id}?repo_id=sample-repo
```

示例：

```http
GET /context/task-package/task_route_post_login?repo_id=sample-repo
```

返回重点字段：

- `target`：本任务目标文件和目标符号。
- `focus_points`：本任务建议关注点。
- `initial_context.type`：固定为 `task_entry`，表示这是轻量任务入口。
- `initial_context.suggested_next_tool`：通常为 `get_task_graph_slice`。
- `initial_context.file_path` / `symbols`：下游 agent 的首轮关注目标。
- `available_tools`：允许继续调用的上下文工具。
- `context_policy`：上下文扩展上限。

注意：阶段 9 后，`initial_context` 不再预塞源码片段、相关符号或调用图。下游 agent 应通过 graph slice 和上下文工具按需读取代码。

### 获取任务局部图

```http
GET /context/tasks/task_route_post_login/graph-slice?repo_id=sample-repo&depth=2
```

返回重点字段：

- `nodes`：任务范围内节点，包含 `relation_to_target`、`priority`、`risk_score`、`reason`。
- `edges`：任务范围内调用关系。
- `boundary_nodes`：超出任务范围或深度限制的相邻节点，也包含 `reason` 和 `risk_score`，但不会继续展开。
- `truncated`：是否发生截断。
- `graph_scope`：固定为 `task-local`。

下游 agent 应优先阅读 `priority` 高、`risk_score` 高、`relation_to_target` 为 `target` / `direct_callee` / `direct_caller` 的节点。约束：该接口只返回任务局部图，不返回完整仓库调用图。

## 4. 按需扩展上下文

### 读取源码片段

```http
GET /context/file-snippet?repo_id=sample-repo&file_path=app/api/auth.py&start_line=1&end_line=80&task_id=task_route_post_login&review_dimension=security
```

返回：

```json
{
  "file_path": "app/api/auth.py",
  "start_line": 1,
  "end_line": 80,
  "content": "..."
}
```

约束：

- 只能读取仓库内路径。
- `../../secret.txt` 这类路径穿越会被拒绝。
- 不要一次请求过大范围源码。

### 获取符号详情

```http
GET /context/node-detail?repo_id=sample-repo&symbol_name=login&task_id=task_route_post_login&review_dimension=security
```

返回：

```json
{
  "node_id": "...",
  "name": "login",
  "qualified_name": "app.api.auth.login",
  "file_path": "app/api/auth.py",
  "start_line": 10,
  "end_line": 13,
  "code": "...",
  "callers": [],
  "callees": []
}
```

### 查询调用关系

```http
GET /context/callees?repo_id=sample-repo&symbol_name=login&depth=1&task_id=task_route_post_login&review_dimension=security
```

```http
GET /context/callers?repo_id=sample-repo&symbol_name=authenticate&depth=1&task_id=task_route_post_login&review_dimension=security
```

建议：

- 默认 `depth=1`。
- 需要更长链路时再提高到 `depth=2`。
- 不要要求完整仓库 graph。

### 获取相关上下文包

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
  "max_files": 3
}
```

返回：

```json
{
  "task_id": "task_route_post_login",
  "target_file": "app/api/auth.py",
  "related_files": [],
  "related_symbols": [],
  "snippets": [],
  "call_graph_slice": {
    "graph_scope": "local",
    "center": "app.api.auth.login",
    "depth": 1,
    "nodes": [],
    "edges": []
  }
}
```

这是下游 agent 扩展上下文的首选入口。

## 5. Context Usage 自动记录

下游 agent 调用上下文接口时，服务会自动写入 `context_usage`。

会记录：

- `task_id`
- `review_dimension`
- `tool_name`
- `target_type`
- `target_name`
- `node_id`
- `file_path`
- `start_line`
- `end_line`
- `lines_returned`
- `created_at`

工具和 usage 类型对应关系：

| 工具 | target_type |
| --- | --- |
| `get_file_snippet` | `file` |
| `get_node_detail` | `symbol` |
| `get_callees` | `graph` |
| `get_callers` | `graph` |
| `trace_call_chain` | `graph` |
| `get_related_context` | `batch_context` |

usage 记录失败不会影响主查询返回。

## 6. 查看覆盖率

请求：

```http
GET /demo/{repo_id}/coverage
```

示例：

```http
GET /demo/sample-repo/coverage
```

返回中重点看：

- `usage_coverage_report.file_coverage`
- `usage_coverage_report.node_coverage`
- `usage_coverage_report.task_completion_rate`
- `usage_coverage_report.covered_files`
- `usage_coverage_report.uncovered_files`
- `usage_coverage_report.usage_records`
- `uncovered_file_reviews`

`uncovered_file_reviews` 可作为补充任务来源，用于覆盖尚未实际读取过的源码文件。

## 7. 下游评审反馈建议

当前模块不保存最终评审结论。如果下游系统需要回传评审结果，建议另建结果表或服务，至少保存：

```json
{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "agent": "security-review-agent",
  "status": "completed",
  "summary": "本任务已检查登录入口的输入校验、认证调用和 token 返回路径。",
  "findings": [
    {
      "severity": "medium",
      "file_path": "app/api/auth.py",
      "start_line": 10,
      "end_line": 13,
      "title": "错误信息需要避免暴露认证细节",
      "evidence_context": ["usage_000001", "usage_000002"]
    }
  ],
  "used_context": ["usage_000001", "usage_000002"],
  "created_at": "2026-06-01T00:00:00Z"
}
```

建议下游反馈包含：

- 任务状态：`pending` / `running` / `completed` / `blocked`。
- 使用过的 `context_usage` 记录。
- 结论引用的文件和行号。
- 如果上下文不足，说明还需要哪些工具或范围。

## 8. 接入注意事项

- 下游 agent 不要直接读取完整仓库源码。
- 下游 agent 不要要求完整仓库 graph。
- 优先使用任务包里的 `initial_context`。
- 上下文不足时，优先调用 `/context/related-context`。
- 所有工具返回值都是 JSON serializable。
- 路径必须是仓库内相对路径。
- 评审结论和风险判断属于下游 agent，不属于本上下文模块。
