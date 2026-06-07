# Review Agent

`agent/review_agent` 是下游 review agent 的基础模块。它不直接解析仓库，也不直接读取 `repo_context` 内部对象，而是通过上下文服务 API 工作。

## 目录结构

```text
agent/
├── docs/          # 新 agent 接入、扩展和协作说明
└── review_agent/
    ├── clients/   # 外部 API client：context API、LLM API
    ├── config/    # 环境变量配置
    └── core/      # agent 任务编排
```

## 调用流程

1. 调用 `/context/task-package/{task_id}` 获取任务包。
2. 调用 `/context/tasks/{task_id}/graph-slice` 获取 task-local graph slice。
3. 调用 `/context/related-context` 按需扩展上下文。
4. 调用模型 API 生成本轮任务状态。
5. 调用 `/context/task-feedback` 回传状态和上下文需求。

## 环境变量

```powershell
$env:CONTEXT_API_BASE_URL = "http://127.0.0.1:8000"
$env:REVIEW_AGENT_PROVIDER = "openai"
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_MODEL = "<model-name>"
```

也可以用 `REVIEW_AGENT_MODEL` 覆盖 provider 默认模型变量。

## 设计约束

- 不把前端代码放进 `agent/`。
- 不直接 import `repo_context` 内部模块。
- 不请求完整仓库源码。
- 不提交最终漏洞报告，只提交任务状态和上下文需求。

## 新 agent 接入

新增 agent 的目录、配置和测试约定见 [docs/new-agent-integration.md](docs/new-agent-integration.md)。
## Function Logic Agent Trace Demo

当前 agent demo 先实现功能逻辑维度：`review_dimension = "function_logic"`。它展示的是 agent 和 AI 的多轮信息流，而不是 context 接口调试台。

启动前先确保 context 服务已经运行，并且目标 `repo_id` 已经通过 `POST /context/index` 构建过索引。然后启动 agent demo：

```powershell
$env:PYTHONPATH = "agent"
$env:CONTEXT_API_BASE_URL = "http://127.0.0.1:8000"
$env:REVIEW_AGENT_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "<your-deepseek-key>"
$env:REVIEW_AGENT_MODEL = "deepseek-v4-flash"
python -m uvicorn review_agent.api.app:app --host 127.0.0.1 --port 8010 --reload
```

打开：

```text
http://127.0.0.1:8010/
```

页面会展示一次功能逻辑 agent run 的完整 trace：

1. agent 读取 `task_package`。
2. agent 读取 task-local `graph_slice` 和初始 `related_context`。
3. agent 把当前上下文和 trace 发给 AI。
4. AI 返回 `call_tool` 或 `final`。
5. 如果是 `call_tool`，agent 执行上下文工具，并把工具结果追加进 trace。
6. 如果是 `final`，agent 生成最终结果并调用 `POST /context/task-feedback`。

trace event 类型包括：

- `task_package`
- `ai_request`
- `ai_response`
- `tool_call`
- `tool_result`
- `final_result`
- `task_feedback`

AI 只决定下一步工具调用意图；真正的工具执行、`repo_id` / `task_id` / `review_dimension` 参数补齐、错误处理和 task-feedback 仍由 agent 代码控制。
