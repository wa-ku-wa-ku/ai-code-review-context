# Context API Reference

本文档面向下游 Agent / 下游工程师，说明上下文处理模块的必接接口、请求参数、返回重点和标准调用顺序。

配套产物：

- `context/docs/api/openapi.json`：从真实 FastAPI 应用导出的 OpenAPI 规范。
- `context/docs/api/postman_collection.json`：可直接导入 Postman 的请求集合。
- `context/docs/api/README.md`：Postman 变量和调用顺序说明。

## 标准调用流程

```text
POST /context/index
GET  /context/tasks?repo_id={repo_id}&review_dimension={review_dimension}
GET  /context/task-package/{task_id}
GET  /context/tasks/{task_id}/graph-slice
POST /context/related-context
GET  /context/file-snippet
GET  /context/node-detail
GET  /context/callees
GET  /context/callers
POST /context/task-feedback
```

`POST /context/index` 是前置步骤。服务启动后还没有任务包，必须先构建索引生成 `review_tasks`。下游 Agent 再按自己的 `review_dimension` 调用 `GET /context/tasks` 查询任务列表，从 `tasks[].task_id` 中读取任务 ID。之后通过任务包确认目标和策略，再通过 task-local graph slice 判断阅读路径；需要源码时再按需调用上下文工具。任务完成、阻塞或上下文不足时，通过 `task-feedback` 反馈状态。

固定评审维度枚举：

| review_dimension | 说明 |
| --- | --- |
| `security` | 安全评审任务 |
| `function_logic` | 功能逻辑评审任务 |
| `coding_style` | 代码风格和可维护性任务 |
| `requirement_consistency` | 需求一致性任务，当前主要作为预留维度 |

## 1. POST /context/index

作用：构建仓库上下文索引，生成仓库摘要、评审任务和初始覆盖率。

该接口必须先成功执行，后续 `GET /context/tasks` 才能按维度查询可领取任务。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 本次仓库分析 ID |
| `repo_path` | Body | string | 是 | 服务端本机可访问的 Python 仓库路径 |
| `db_path` | Body | string | 否 | SQLite 索引文件路径 |

示例：

```http
POST /context/index
```

```json
{
  "repo_id": "sample-repo",
  "repo_path": "tests/fixtures/sample_repo",
  "db_path": ".demo_data/sample-repo.db"
}
```

`repo_id = "sample-repo"` 可以换成你自己的仓库分析 ID，例如 `"payment-service"`；`repo_path = "tests/fixtures/sample_repo"` 可以换成服务端本机可访问的真实 Python 仓库路径，例如 `"D:\demo_repos\my_python_repo"`。

返回重点：`repo_summary`、`review_tasks`、`task_coverage_report`、`usage_coverage_report`。

## 2. GET /context/tasks

作用：按固定评审维度查询任务列表，供对应下游 agent 领取任务。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Query | string | 是 | 仓库 ID |
| `review_dimension` | Query | enum | 是 | 固定枚举：`security`、`function_logic`、`coding_style`、`requirement_consistency` |

示例：

```http
GET /context/tasks?repo_id=sample-repo&review_dimension=security
```

返回重点：

- `tasks[]`：该维度下可处理的任务列表。
- `tasks[].task_id`：后续调用任务包接口需要使用的任务 ID。
- `tasks[].review_dimension`：一定等于请求中的 `review_dimension`。

## 3. GET /context/task-package/{task_id}

作用：获取单个任务包，包括目标、轻量 `initial_context`、可用工具和上下文策略。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `task_id` | Path | string | 是 | 任务 ID |
| `repo_id` | Query | string | 是 | 仓库 ID |

示例：

```http
GET /context/task-package/task_route_post_login?repo_id=sample-repo
```

下游重点读取：

- `target`：目标文件和目标符号。
- `focus_points`：本任务关注点。
- `initial_context.suggested_next_tool`：通常是 `get_task_graph_slice`。
- `available_tools`：允许继续调用的上下文工具。
- `context_policy`：上下文扩展限制，包含 `allow_full_graph=false` 和 `max_graph_depth`。

## 4. GET /context/tasks/{task_id}/graph-slice

作用：获取 task-local graph slice。该接口不返回完整仓库 graph。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `task_id` | Path | string | 是 | 任务 ID |
| `repo_id` | Query | string | 是 | 仓库 ID |
| `depth` | Query | integer | 否 | 局部图深度，默认 2，受 `context_policy.max_graph_depth` 限制 |

示例：

```http
GET /context/tasks/task_route_post_login/graph-slice?repo_id=sample-repo&depth=2
```

返回重点：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | array | 任务范围内节点，包含 `relation_to_target`、`priority`、`risk_score`、`reason` |
| `edges` | array | 任务范围内调用边 |
| `boundary_nodes` | array | 超出任务范围或深度限制的相邻节点，不继续展开 |
| `truncated` | boolean | 是否发生截断 |
| `target` | object | 当前任务目标 |
| `depth` | integer | 实际使用深度 |

下游重点读取：优先阅读 `priority` 高、`risk_score` 高、`relation_to_target` 为 `target` / `direct_callee` / `direct_caller` 的节点。

## 5. POST /context/related-context

作用：在 graph slice 后补充源码片段、相关符号和局部调用上下文。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 仓库 ID |
| `task_id` | Body | string | 否 | 任务 ID，建议必传 |
| `target_file` | Body | string | 否 | 目标文件 |
| `review_dimension` | Body | enum | 否 | 评审维度，建议必传。固定枚举：`security`、`function_logic`、`coding_style`、`requirement_consistency` |
| `tags` | Body | array | 否 | 任务标签 |
| `max_depth` | Body | integer | 否 | 调用关系扩展深度 |
| `max_files` | Body | integer | 否 | 最大返回文件数 |

示例：

```json
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

返回重点：`snippets`、`related_symbols`、`call_graph_slice`、`related_files`。

## 5. 精确上下文工具

### GET /context/file-snippet

读取源码片段。路径穿越如 `../../secret.txt` 会被拒绝。

必填参数：`repo_id`、`file_path`。建议同时传 `task_id` 和 `review_dimension`。

```http
GET /context/file-snippet?repo_id=sample-repo&file_path=app/api/auth.py&start_line=1&end_line=80&task_id=task_route_post_login&review_dimension=security
```

### GET /context/node-detail

获取函数、类、方法或路由节点详情。

```http
GET /context/node-detail?repo_id=sample-repo&symbol_name=login&task_id=task_route_post_login&review_dimension=security
```

### GET /context/callees

查询当前符号调用了哪些符号。

```http
GET /context/callees?repo_id=sample-repo&symbol_name=login&depth=1&task_id=task_route_post_login&review_dimension=security
```

### GET /context/callers

查询哪些符号调用了当前符号。

```http
GET /context/callers?repo_id=sample-repo&symbol_name=authenticate&depth=1&task_id=task_route_post_login&review_dimension=security
```

## 6. POST /context/task-feedback

作用：反馈任务执行状态、上下文是否足够、是否需要补充上下文。该接口不是最终漏洞结果提交接口。

参数：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 仓库 ID |
| `task_id` | Body | string | 是 | 任务 ID |
| `agent` | Body | string | 是 | 下游 Agent 名称 |
| `status` | Body | string | 是 | `completed`、`blocked`、`skipped` 等 |
| `context_sufficient` | Body | boolean | 是 | 当前上下文是否足够 |
| `feedback_type` | Body | string | 是 | `task_status`、`context_request` 等 |
| `message` | Body | string | 否 | 说明 |
| `need_more_context` | Body | boolean | 否 | 是否需要更多上下文 |
| `requested_context` | Body | array | 否 | 需要补充的源码、符号或调用关系 |
| `downstream_result_ref` | Body | string | 否 | 最终结果在更下游系统中的引用 |
| `created_at` | Body | string | 否 | 客户端创建时间 |

完成示例：

```json
{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "agent": "security-review-agent",
  "status": "completed",
  "context_sufficient": true,
  "feedback_type": "task_status",
  "message": "任务已完成，上下文足够支持本轮评审。",
  "need_more_context": false,
  "requested_context": [],
  "downstream_result_ref": "review-result-0001"
}
```

阻塞示例：

```json
{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "agent": "security-review-agent",
  "status": "blocked",
  "context_sufficient": false,
  "feedback_type": "context_request",
  "message": "当前任务缺少认证函数的上游调用入口，需要补充调用者信息。",
  "need_more_context": true,
  "requested_context": [
    {"type": "callers", "symbol_name": "authenticate", "depth": 2}
  ],
  "downstream_result_ref": null
}
```

返回重点：`accepted`、`feedback_id`、`next_action`、`status`、`context_sufficient`。

## Context Usage

`context_usage` 是服务端自动记录机制，用于覆盖率统计和调试分析。下游 Agent 不需要直接写 `context_usage`，只需要在上下文工具调用中携带：

- `task_id`
- `review_dimension`

服务端会自动记录工具名、目标文件/符号、返回行数、任务 ID 和评审维度。
