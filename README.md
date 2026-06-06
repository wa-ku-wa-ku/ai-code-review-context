# AI Code Review Workspace

这是一个仓库级 AI 代码评审实验工程，当前拆成两个并行模块：

```text
context/
└── repo_context/      # 上下文处理模块：索引、AST、任务包、上下文 API

agent/
└── review_agent/      # 下游 agent：调用上下文 API 和模型 API
```

## 模块边界

- `context/` 负责把 Python 仓库整理成可查询、可追踪、可限制的上下文服务。
- `agent/` 负责按任务调用 `context` 暴露的 API，并把任务状态反馈回去。
- 两个模块通过 HTTP API 和环境配置解耦；`agent` 不直接调用 `repo_context` 内部实现。
- 前端后续应单独放在 `frontend/`，不要混入 `context/` 或 `agent/`。

## 快速开始

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

从仓库根目录启动上下文服务：

```powershell
$env:PYTHONPATH = "context"
python -m uvicorn repo_context.api.app:app --host 127.0.0.1 --port 8000 --reload
```

下游 agent 需要模型环境变量：

```powershell
$env:REVIEW_AGENT_PROVIDER = "openai"
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_MODEL = "<model-name>"
```

## 文档位置

- 上下文模块说明：[context/README.md](context/README.md)
- 上下文 API 文档：[context/docs/context-api-reference.md](context/docs/context-api-reference.md)
- 下游接入说明：[context/docs/downstream-agent-integration.md](context/docs/downstream-agent-integration.md)
- agent 模块说明：[agent/README.md](agent/README.md)
- 新 agent 接入指南：[agent/docs/new-agent-integration.md](agent/docs/new-agent-integration.md)
