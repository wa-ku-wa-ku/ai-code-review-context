# Review Agent 上下文工具接入文档

本文档面向下游 review agent / 工程服务，说明下游如何通过上下文模块提供的 API 获取仓库上下文、按需调用上下文工具，并在任务结束后反馈任务状态和上下文需求。

上下文模块的核心定位：**把仓库代码组织成可查询、可限制、可追踪的上下文服务，供下游 agent 执行仓库级代码评审。**

最终漏洞判断、报告生成、风险归档等内容由更下游评审系统处理；上下文模块重点负责：

1. 生成评审任务包；
2. 提供上下文工具接口；
3. 记录上下文实际使用情况；
4. 接收任务状态与上下文需求反馈。

---

## 1. 下游必须接入的接口

> **重点：这里的“必须接入”指下游 agent 必须实现这些接口的调用逻辑。** 这些接口由上下文模块提供，下游负责按照标准流程调用。

| 接入等级 | 接口 | 下游动作 | 作用 |
| --- | --- | --- | --- |
| **必须调用** | `GET /context/task-package/{task_id}` | 每个评审任务开始前调用 | 获取任务目标、初始上下文、可用工具和上下文限制 |
| **必须调用** | `POST /context/task-feedback` | 每个评审任务完成、阻塞或跳过时调用 | 反馈任务状态、上下文是否足够、是否需要补充上下文 |
| **必须优先支持** | `POST /context/related-context` | 初始上下文不足时优先调用 | 获取任务相关的源码片段、符号和局部调用图 |
| **必须支持** | `GET /context/file-snippet` | 需要精确源码时调用 | 按文件路径和行号读取源码片段 |
| **必须支持** | `GET /context/node-detail` | 需要理解函数/类时调用 | 获取符号代码、位置、调用者和被调用者 |
| **按需支持** | `GET /context/callees` | 需要向下追踪调用链时调用 | 查询当前符号调用了哪些符号 |
| **按需支持** | `GET /context/callers` | 需要向上追踪入口时调用 | 查询哪些符号调用了当前符号 |

工程初始化阶段通常还会使用：

| 接口 | 使用方 | 作用 |
| --- | --- | --- |
| `POST /context/index` | 工程服务 / 调度服务 | 为目标仓库构建索引并生成 `review_tasks` |
| `GET /demo/{repo_id}/coverage` | 工程服务 / 验收方 | 查看实际上下文读取覆盖率 |

---

## 2. 下游 Agent 标准调用流程

该流程用于约束下游 agent 如何使用上下文工具。它不是新的接口，而是建议下游 agent 按这个顺序编写调用逻辑。

```text
1. 工程服务调用 /context/index 构建仓库索引，得到 review_tasks
2. 调度器把单个 task 分配给对应 review agent
3. agent 调用 /context/task-package/{task_id} 获取任务包
4. agent 优先阅读 initial_context
5. agent 判断上下文是否足够
6. 上下文不足时，优先调用 /context/related-context
7. 需要精确信息时，再调用 file-snippet / node-detail / callers / callees
8. 任务完成、阻塞或跳过时，调用 /context/task-feedback 反馈状态
```

推荐顺序：

```text
task_package.initial_context
        ↓
/context/related-context
        ↓
/context/file-snippet 或 /context/node-detail
        ↓
/context/callees 或 /context/callers
        ↓
/context/task-feedback
```

### 示例：登录接口安全评审

任务目标：检查 `POST /login` 的输入校验、认证调用和异常处理。

```json
{
  "task_id": "task_route_post_login",
  "review_dimension": "security",
  "target": {
    "file_path": "app/api/auth.py",
    "symbols": ["login"]
  },
  "focus_points": ["输入校验", "身份认证", "异常处理"]
}
```

下游 agent 应该先调用任务包接口：

```http
GET /context/task-package/task_route_post_login?repo_id=sample-repo
```

如果任务包中的 `initial_context` 已经包含 `login()` 的入口代码，agent 先基于这部分上下文评审。

如果发现 `login()` 调用了 `authenticate()`，但当前上下文缺少认证函数实现，agent 再调用：

```http
GET /context/node-detail?repo_id=sample-repo&symbol_name=authenticate&task_id=task_route_post_login&review_dimension=security
```

如果需要查看认证函数的上游入口，agent 再调用：

```http
GET /context/callers?repo_id=sample-repo&symbol_name=authenticate&depth=1&task_id=task_route_post_login&review_dimension=security
```

任务结束后，agent 调用反馈接口：

```http
POST /context/task-feedback
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "agent": "security-review-agent",
  "status": "completed",
  "context_sufficient": true,
  "feedback_type": "task_status",
  "message": "登录入口安全评审已完成，当前上下文足够。",
  "need_more_context": false,
  "requested_context": [],
  "downstream_result_ref": "review-result-20260601-0001"
}
```

---

## 3. 接口请求与返回总览

| 接口 | 参数位置 | 主要请求参数 | 主要返回结果 |
| --- | --- | --- | --- |
| `GET /context/task-package/{task_id}` | Path + Query | `task_id`, `repo_id` | `target`, `initial_context`, `available_tools`, `context_policy` |
| `POST /context/related-context` | Body | `repo_id`, `task_id`, `target_file`, `review_dimension`, `tags`, `max_depth`, `max_files` | `snippets`, `related_symbols`, `call_graph_slice` |
| `GET /context/file-snippet` | Query | `repo_id`, `file_path`, `start_line`, `end_line`, `task_id`, `review_dimension` | `content`, `start_line`, `end_line` |
| `GET /context/node-detail` | Query | `repo_id`, `symbol_name`, `task_id`, `review_dimension` | `code`, `file_path`, `callers`, `callees` |
| `GET /context/callees` | Query | `repo_id`, `symbol_name`, `depth`, `task_id`, `review_dimension` | 被调用符号列表、局部调用边 |
| `GET /context/callers` | Query | `repo_id`, `symbol_name`, `depth`, `task_id`, `review_dimension` | 调用者符号列表、局部调用边 |
| `POST /context/task-feedback` | Body | `repo_id`, `task_id`, `agent`, `status`, `context_sufficient`, `requested_context` | `accepted`, `feedback_id`, `next_action` |

---

## 4. 任务包接口：GET /context/task-package/{task_id}

### 作用

下游 agent 通过该接口获取单个评审任务的完整任务包，包括任务目标、初始上下文、可用工具和上下文扩展限制。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `task_id` | Path | string | 是 | 当前评审任务 ID |
| `repo_id` | Query | string | 是 | 当前仓库 ID |

### 请求示例

```http
GET /context/task-package/task_route_post_login?repo_id=sample-repo
```

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 任务 ID |
| `task_type` | string | 任务类型，例如 `entrypoint_review` |
| `review_dimension` | string | 评审维度，例如 `security` |
| `priority` | string | 任务优先级 |
| `target` | object | 任务目标文件和目标符号 |
| `focus_points` | array | 建议关注点 |
| `initial_context` | object | 初始上下文，包含源码片段、相关符号和局部调用图 |
| `available_tools` | array | 当前任务允许继续调用的上下文工具 |
| `context_policy` | object | 上下文扩展上限，例如最大深度、最大文件数、最大行数 |

### 返回示例

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
  "focus_points": ["输入校验", "身份认证", "异常处理"],
  "initial_context": {
    "file_snippets": [],
    "related_symbols": [],
    "call_graph_slice": {
      "graph_scope": "local",
      "center": "app.api.auth.login",
      "depth": 1,
      "nodes": [],
      "edges": []
    }
  },
  "available_tools": [
    "get_file_snippet",
    "get_node_detail",
    "get_related_context",
    "get_callers",
    "get_callees"
  ],
  "context_policy": {
    "max_depth": 2,
    "max_snippet_lines": 120,
    "max_files": 6,
    "allow_expand": true
  }
}
```

### 下游重点读取

- `target`：确定本任务评审的文件和符号；
- `focus_points`：确定评审关注点；
- `initial_context`：作为第一轮上下文；
- `available_tools`：决定后续可以调用哪些上下文工具；
- `context_policy`：控制扩展上下文范围。

---

## 5. 相关上下文工具：POST /context/related-context

### 作用

当任务包中的初始上下文不足时，下游 agent 应该优先调用该接口。它会根据任务目标、评审维度和标签返回一组相关文件、相关符号、源码片段和局部调用图。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 仓库 ID |
| `task_id` | Body | string | 是 | 当前评审任务 ID |
| `target_file` | Body | string | 是 | 当前任务目标文件 |
| `review_dimension` | Body | string | 是 | 当前评审维度 |
| `tags` | Body | array | 否 | 任务标签，例如 `api_entry`、`auth` |
| `max_depth` | Body | integer | 否 | 调用关系扩展深度 |
| `max_files` | Body | integer | 否 | 最多返回文件数 |

### 请求示例

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

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 当前任务 ID |
| `target_file` | string | 当前任务目标文件 |
| `related_files` | array | 相关文件列表 |
| `related_symbols` | array | 相关符号列表 |
| `snippets` | array | 返回的源码片段 |
| `call_graph_slice` | object | 任务局部调用图 |

### 返回示例

```json
{
  "task_id": "task_route_post_login",
  "target_file": "app/api/auth.py",
  "related_files": ["app/services/auth_service.py"],
  "related_symbols": ["login", "authenticate"],
  "snippets": [
    {
      "file_path": "app/services/auth_service.py",
      "start_line": 1,
      "end_line": 80,
      "content": "..."
    }
  ],
  "call_graph_slice": {
    "graph_scope": "local",
    "center": "app.api.auth.login",
    "depth": 1,
    "nodes": [],
    "edges": []
  }
}
```

### 下游重点读取

- `snippets`：直接用于补充评审上下文；
- `related_symbols`：作为后续 `node-detail`、`callers`、`callees` 的候选目标；
- `call_graph_slice`：帮助判断当前任务附近的调用关系。

---

## 6. 源码片段工具：GET /context/file-snippet

### 作用

按文件路径和行号读取源码片段。适合在 agent 已经知道目标文件和行号范围时使用。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Query | string | 是 | 仓库 ID |
| `file_path` | Query | string | 是 | 仓库内相对路径 |
| `start_line` | Query | integer | 是 | 起始行号 |
| `end_line` | Query | integer | 是 | 结束行号 |
| `task_id` | Query | string | 建议必填 | 当前任务 ID，用于 usage 记录 |
| `review_dimension` | Query | string | 建议必填 | 当前评审维度，用于 usage 记录 |

### 请求示例

```http
GET /context/file-snippet?repo_id=sample-repo&file_path=app/api/auth.py&start_line=1&end_line=80&task_id=task_route_post_login&review_dimension=security
```

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_path` | string | 文件路径 |
| `start_line` | integer | 实际返回起始行 |
| `end_line` | integer | 实际返回结束行 |
| `content` | string | 源码内容 |

### 返回示例

```json
{
  "file_path": "app/api/auth.py",
  "start_line": 1,
  "end_line": 80,
  "content": "..."
}
```

---

## 7. 符号详情工具：GET /context/node-detail

### 作用

获取函数、类或方法等符号的详情，包括符号位置、源码、调用者和被调用者。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Query | string | 是 | 仓库 ID |
| `symbol_name` | Query | string | 是 | 符号名称，例如 `login` |
| `task_id` | Query | string | 建议必填 | 当前任务 ID，用于 usage 记录 |
| `review_dimension` | Query | string | 建议必填 | 当前评审维度，用于 usage 记录 |

### 请求示例

```http
GET /context/node-detail?repo_id=sample-repo&symbol_name=login&task_id=task_route_post_login&review_dimension=security
```

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `node_id` | string | 符号节点 ID |
| `name` | string | 符号短名称 |
| `qualified_name` | string | 符号完整名称 |
| `file_path` | string | 符号所在文件 |
| `start_line` | integer | 起始行号 |
| `end_line` | integer | 结束行号 |
| `code` | string | 符号源码 |
| `callers` | array | 调用该符号的上游符号 |
| `callees` | array | 该符号调用的下游符号 |

### 返回示例

```json
{
  "node_id": "node_auth_login",
  "name": "login",
  "qualified_name": "app.api.auth.login",
  "file_path": "app/api/auth.py",
  "start_line": 10,
  "end_line": 35,
  "code": "...",
  "callers": [],
  "callees": ["authenticate", "create_token"]
}
```

---

## 8. 调用关系工具：GET /context/callees 与 GET /context/callers

### 作用

`callees` 用于向下查看当前符号调用了哪些符号；`callers` 用于向上查看哪些符号调用了当前符号。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Query | string | 是 | 仓库 ID |
| `symbol_name` | Query | string | 是 | 符号名称 |
| `depth` | Query | integer | 否 | 调用关系深度，建议默认 `1` |
| `task_id` | Query | string | 建议必填 | 当前任务 ID，用于 usage 记录 |
| `review_dimension` | Query | string | 建议必填 | 当前评审维度，用于 usage 记录 |

### 请求示例

```http
GET /context/callees?repo_id=sample-repo&symbol_name=login&depth=1&task_id=task_route_post_login&review_dimension=security
```

```http
GET /context/callers?repo_id=sample-repo&symbol_name=authenticate&depth=1&task_id=task_route_post_login&review_dimension=security
```

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `center` | string | 查询中心符号 |
| `depth` | integer | 查询深度 |
| `nodes` | array | 调用图节点 |
| `edges` | array | 调用图边 |

### 返回示例

```json
{
  "center": "app.api.auth.login",
  "depth": 1,
  "nodes": [
    {"name": "login", "file_path": "app/api/auth.py"},
    {"name": "authenticate", "file_path": "app/services/auth_service.py"}
  ],
  "edges": [
    {"source": "login", "target": "authenticate", "type": "calls"}
  ]
}
```

---

## 9. 下游任务反馈接口：POST /context/task-feedback

### 作用

该接口用于接收下游 agent 对当前评审任务的执行反馈。它不是最终漏洞结果回传接口，而是任务协作反馈接口。

下游应该通过该接口反馈：

1. 当前任务状态；
2. 当前上下文是否足够；
3. 是否需要补充源码、符号或调用关系；
4. 最终评审结果是否已经交给更下游系统处理。

### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 仓库 ID |
| `task_id` | Body | string | 是 | 当前任务 ID |
| `agent` | Body | string | 是 | 提交反馈的 agent 名称 |
| `status` | Body | string | 是 | 任务状态：`running`、`completed`、`blocked`、`skipped` |
| `context_sufficient` | Body | boolean | 是 | 当前上下文是否足够 |
| `feedback_type` | Body | string | 是 | 反馈类型：`task_status`、`context_request`、`blocked_reason` |
| `message` | Body | string | 否 | 简要说明 |
| `need_more_context` | Body | boolean | 是 | 是否需要补充上下文 |
| `requested_context` | Body | array | 否 | 需要补充的上下文范围 |
| `downstream_result_ref` | Body | string/null | 否 | 更下游结果系统中的结果引用 |
| `created_at` | Body | string | 否 | 反馈时间，可由服务端生成 |

### 请求示例：任务完成

```http
POST /context/task-feedback
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "task_id": "task_route_post_login",
  "agent": "security-review-agent",
  "status": "completed",
  "context_sufficient": true,
  "feedback_type": "task_status",
  "message": "当前任务已完成，上下文足够支持安全维度评审。",
  "need_more_context": false,
  "requested_context": [],
  "downstream_result_ref": "review-result-20260601-0001"
}
```

### 请求示例：上下文不足

```http
POST /context/task-feedback
Content-Type: application/json

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
    {
      "type": "callers",
      "symbol_name": "authenticate",
      "depth": 2,
      "reason": "需要确认认证函数是否被多个入口复用"
    },
    {
      "type": "file_snippet",
      "file_path": "app/services/auth_service.py",
      "start_line": 1,
      "end_line": 120,
      "reason": "需要查看认证服务的完整实现"
    }
  ],
  "downstream_result_ref": null
}
```

### 返回字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `accepted` | boolean | 是否接收反馈 |
| `feedback_id` | string | 反馈记录 ID |
| `task_id` | string | 对应任务 ID |
| `next_action` | string | 建议后续动作，例如 `none`、`generate_supplement_task` |
| `message` | string | 服务端说明 |

### 返回示例

```json
{
  "accepted": true,
  "feedback_id": "feedback_000001",
  "task_id": "task_route_post_login",
  "next_action": "none",
  "message": "feedback received"
}
```

---

## 10. Context Usage 自动记录

`context_usage` 是上下文模块内部的自动记录机制，主要用于覆盖率统计和调试分析。

> **下游需要配合的地方：调用上下文工具接口时，请携带 `task_id` 和 `review_dimension`。**

下游 agent 需要传递这两个参数，服务端会自动记录本次调用使用了哪个工具、读取了哪个文件或符号、返回了哪些行号范围。

| 参数 | 下游为什么要带 |
| --- | --- |
| `task_id` | 用于判断某个任务实际读取过哪些上下文 |
| `review_dimension` | 用于区分安全、性能、可维护性等不同评审维度 |

说明：

- 下游 agent 只需要传参数，usage 写入由上下文模块自动完成。
- usage 记录失败时，主查询结果仍然正常返回。
- usage 数据用于计算实际上下文覆盖率。
- `task-feedback` 只反馈任务状态和上下文需求，最终 findings 由更下游系统处理。

---

## 11. 初始化与覆盖率接口

### POST /context/index

#### 作用

为目标 Python 仓库构建索引，生成仓库摘要、符号索引、调用关系和 `review_tasks`。

#### 请求参数

| 参数 | 位置 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- | --- |
| `repo_id` | Body | string | 是 | 仓库 ID |
| `repo_path` | Body | string | 是 | 服务端本机可访问的仓库目录 |
| `db_path` | Body | string | 是 | SQLite 索引文件路径 |

#### 请求示例

```http
POST /context/index
Content-Type: application/json

{
  "repo_id": "sample-repo",
  "repo_path": "tests/fixtures/sample_repo",
  "db_path": ".demo_data/sample-repo.db"
}
```

#### 返回重点字段

| 字段 | 说明 |
| --- | --- |
| `repo_summary` | 仓库摘要 |
| `review_tasks` | 下游 agent 要处理的任务列表 |
| `task_coverage_report` | 任务规划覆盖率 |
| `usage_coverage_report` | 实际上下文读取覆盖率 |

### GET /demo/{repo_id}/coverage

#### 作用

查看下游 agent 实际读取过哪些文件和符号，用于验收覆盖率和发现未覆盖范围。

#### 请求示例

```http
GET /demo/sample-repo/coverage
```

#### 返回重点字段

| 字段 | 说明 |
| --- | --- |
| `usage_coverage_report.file_coverage` | 文件覆盖率 |
| `usage_coverage_report.node_coverage` | 符号覆盖率 |
| `usage_coverage_report.task_completion_rate` | 任务完成率 |
| `usage_coverage_report.covered_files` | 已覆盖文件 |
| `usage_coverage_report.uncovered_files` | 未覆盖文件 |
| `uncovered_file_reviews` | 可作为补充任务来源的未覆盖文件任务 |

---

## 12. Python 调用示例

下面示例展示下游 agent 如何获取任务包、扩展相关上下文，并提交任务反馈。

```python
import requests

BASE_URL = "http://localhost:8080"
REPO_ID = "sample-repo"
TASK_ID = "task_route_post_login"
AGENT = "security-review-agent"


def get_task_package():
    resp = requests.get(
        f"{BASE_URL}/context/task-package/{TASK_ID}",
        params={"repo_id": REPO_ID}
    )
    resp.raise_for_status()
    return resp.json()


def get_related_context(task):
    target = task["target"]
    resp = requests.post(
        f"{BASE_URL}/context/related-context",
        json={
            "repo_id": REPO_ID,
            "task_id": TASK_ID,
            "target_file": target["file_path"],
            "review_dimension": task["review_dimension"],
            "tags": task.get("tags", []),
            "max_depth": 1,
            "max_files": 3
        }
    )
    resp.raise_for_status()
    return resp.json()


def get_node_detail(symbol_name, review_dimension):
    resp = requests.get(
        f"{BASE_URL}/context/node-detail",
        params={
            "repo_id": REPO_ID,
            "symbol_name": symbol_name,
            "task_id": TASK_ID,
            "review_dimension": review_dimension
        }
    )
    resp.raise_for_status()
    return resp.json()


def submit_feedback(status, context_sufficient, message, requested_context=None):
    need_more_context = not context_sufficient
    resp = requests.post(
        f"{BASE_URL}/context/task-feedback",
        json={
            "repo_id": REPO_ID,
            "task_id": TASK_ID,
            "agent": AGENT,
            "status": status,
            "context_sufficient": context_sufficient,
            "feedback_type": "context_request" if need_more_context else "task_status",
            "message": message,
            "need_more_context": need_more_context,
            "requested_context": requested_context or [],
            "downstream_result_ref": None
        }
    )
    resp.raise_for_status()
    return resp.json()


task = get_task_package()

# 1. 优先使用任务包中的 initial_context
initial_context = task.get("initial_context", {})

# 2. 上下文不足时，优先扩展相关上下文
related_context = get_related_context(task)

# 3. 需要查看具体符号时，再调用符号详情工具
login_detail = get_node_detail("login", task["review_dimension"])

# 4. 任务结束后提交反馈
submit_feedback(
    status="completed",
    context_sufficient=True,
    message="任务已完成，上下文足够支持本轮评审。"
)
```

---

## 13. 接入检查清单

下游接入时可以按下面清单验收：

- [ ] 能从 `/context/index` 返回值中读取 `review_tasks`。
- [ ] 每个任务开始前能调用 `/context/task-package/{task_id}`。
- [ ] agent 会优先使用 `initial_context`。
- [ ] 上下文不足时会优先调用 `/context/related-context`。
- [ ] agent 支持按需调用 `file-snippet`、`node-detail`、`callers`、`callees`。
- [ ] 所有上下文工具调用都会带上 `task_id` 和 `review_dimension`。
- [ ] 每个任务结束、阻塞或跳过时会调用 `/context/task-feedback`。
- [ ] 任务反馈中只提交任务状态和上下文需求，最终评审结果交给更下游系统处理。
