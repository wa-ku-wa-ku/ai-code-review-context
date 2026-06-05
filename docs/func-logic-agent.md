# 功能逻辑判断 Agent (func-logic-agent)

## 项目定位

本项目是 `ai-code-review-context` 的下游消费 Agent。它不修改 context 服务的任何代码，仅通过 HTTP API 获取代码上下文，完成 **function_logic** 维度的审查后，通过 `POST /context/task-feedback` 提交结果。

```
┌──────────────────────────────┐
│  ai-code-review-context      │
│  (FastAPI + SQLite)          │  ← 不修改，只调用
│  :8000                       │
└──────────┬───────────────────┘
           │ HTTP API
           ▼
┌──────────────────────────────┐
│  func-logic-agent            │
│  规则引擎 → LLM 判断 → 反馈  │
└──────────────────────────────┘
```

---

## 目录结构

```
func-logic-agent/
├── func_logic_agent/
│   ├── __init__.py              # 导出 AgentConfig, FuncLogicAgent
│   ├── config.py                # 全部可调参数
│   ├── models.py                # 内部数据模型
│   ├── client/
│   │   └── context_api_client.py  # HTTP 客户端（覆盖 context 全部端点）
│   ├── rules/
│   │   └── rule_engine.py       # 7 条确定性规则，微秒级完成
│   ├── llm/
│   │   ├── prompts.py           # 系统/用户 prompt 模板
│   │   └── llm_judge.py         # LLM 调用（Anthropic / OpenAI 双后端）
│   └── orchestrator.py          # 主循环：索引→筛选→采集→判断→反馈
├── tests/                       # 51 个测试（全部 mock，无需启动服务）
├── requirements.txt
└── pytest.ini
```

---

## 配置说明

所有参数通过 `AgentConfig` 管理，支持三种初始化方式：

### 直接构造

```python
from func_logic_agent import AgentConfig

config = AgentConfig(
    repo_id="my-repo",
    context_api_base="http://127.0.0.1:8000",
    llm_provider="openai",          # "anthropic" (默认) 或 "openai"
    llm_model="gpt-4o",
    openai_api_key="sk-xxx",
    openai_base_url="https://api.openai.com/v1",
)
```

### 环境变量

```bash
export CONTEXT_API_BASE=http://127.0.0.1:8000
export REPO_ID=my-repo
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.openai.com/v1
```

```python
config = AgentConfig.from_env(repo_id="my-repo")
```

### JSON 文件

```json
{
    "repo_id": "my-repo",
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "openai_base_url": "http://localhost:8080/v1"
}
```

```python
config = AgentConfig.from_json("config.json")
```

### 全部参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context_api_base` | str | `http://127.0.0.1:8000` | context 服务地址 |
| `repo_id` | str | `""` | 仓库标识，必须与索引时一致 |
| `llm_provider` | str | `anthropic` | LLM 后端：`anthropic` 或 `openai` |
| `llm_model` | str | `claude-sonnet-4-20250514` | 模型名称 |
| `llm_max_tokens` | int | `4096` | 最大输出 token |
| `llm_temperature` | float | `0.1` | 生成温度（低值 = 确定性高） |
| `openai_api_key` | str | `""` | OpenAI API key（仅 openai 后端） |
| `openai_base_url` | str | `""` | 自定义 base URL（兼容 vLLM/Ollama/Azure） |
| `max_context_retries` | int | `3` | 反馈循环最大重试次数 |
| `max_tasks_per_run` | int | `50` | 单次运行处理任务上限 |
| `request_timeout` | float | `30.0` | HTTP 请求超时（秒） |
| `agent_name` | str | `func-logic-agent` | 提交反馈时的 agent 标识 |
| `graph_node_count_high` | int | `15` | 规则 R1：超过此数视为复杂图 |
| `graph_node_count_low` | int | `3` | 规则 R1/R7：低于此数视为平凡图 |
| `risk_score_threshold` | int | `40` | 规则 R2：风险分阈值 |

---

## 核心流程

```
1. 索引仓库
   POST /context/index → 获取 review_tasks

2. 过滤任务
   只保留 review_dimension == "function_logic"
   按优先级排序：high → medium → low

3. 对每个任务执行以下管道：

   ┌─────────────────────────────────────────────────┐
   │ 3a. 获取任务包                                    │
   │     GET /context/task-package/{task_id}           │
   │                                                   │
   │ 3b. 获取任务局部调用图                             │
   │     GET /context/tasks/{task_id}/graph-slice      │
   │                                                   │
   │ 3c. 规则引擎预筛选（7 条规则，微秒级）              │
   │     → should_skip? → 提交 skipped 反馈，跳过       │
   │     → 否则携带 focus_areas 进入 LLM               │
   │                                                   │
   │ 3d. 采集详细上下文                                │
   │     对 priority >= 70 的节点：GET /context/node-detail  │
   │     对目标文件：GET /context/file-snippet          │
   │     （自动去重，不重复请求已获取的节点/文件）        │
   │                                                   │
   │ 3e. LLM 判断                                     │
   │     发送系统 prompt + 用户 prompt（分层组装）       │
   │     解析 JSON 响应 → LLMJudgmentResult            │
   │                                                   │
   │ 3f. 提交反馈                                      │
   │     POST /context/task-feedback                   │
   │     → 如果 confidence < 0.5 且返回 provide_more_context：│
   │       补充上下文，重新判断（最多 max_context_retries 次）│
   │     → 否则结束该任务                              │
   └─────────────────────────────────────────────────┘
```

---

## API 调用原则

### 1. 只读不写

Agent 对 context 服务的所有调用都是 **读操作**（GET）或 **状态反馈**（POST task-feedback）。不会修改索引数据、不会写入代码文件、不会改变 context 服务的内部状态。

### 2. 先索引后查询

`POST /context/index` 必须最先调用。它会构建 SQLite 索引并返回任务列表。后续所有查询依赖索引已存在。索引是幂等的——对同一 `repo_id` 重复调用会覆盖旧索引。

### 3. 按任务维度消费

不是一次性拉取全部源码，而是按 `task_id` 逐个获取：
- 先拿轻量的 `task-package`（只有目标、关注点、策略，不含源码）
- 再拿局部 `graph-slice`（只有任务附近的调用关系子图）
- 最后按需拿 `node-detail` / `file-snippet`（精确的源码片段）

这种"渐进式上下文获取"避免了一次性灌入整个仓库。

### 4. 反馈循环

`POST /context/task-feedback` 的 `need_more_context` 字段控制循环：
- `false` → 服务端返回 `next_action: "continue_downstream"`，任务结束
- `true` → 服务端返回 `next_action: "provide_more_context"`，Agent 应补充上下文后重新判断

Agent 侧通过 `max_context_retries` 限制循环次数，防止无限循环。

### 5. 上下文去重

Agent 内部维护 `GatheredContext`，通过 `fetched_node_ids` 和 `fetched_file_ranges` 集合追踪已获取的内容。同一个节点出现在图切片和 callee 列表中时，只请求一次。

### 6. LLM 后端可替换

通过 `llm_provider` 配置切换：
- `anthropic` → 使用 `anthropic.AsyncAnthropic`
- `openai` → 使用 `openai.AsyncOpenAI`，支持任何 OpenAI 兼容接口（OpenAI、Azure、vLLM、Ollama、DeepSeek 等）

切换后端不需要改代码，只改配置。

---

## 规则引擎

7 条确定性规则，在 LLM 调用前执行，用于分流和聚焦：

| 编号 | 规则 | 触发条件 | 作用 |
|------|------|----------|------|
| R1 | 图复杂度 | 节点数 >15 或 <3 | 标记复杂/平凡图 |
| R2 | 高风险节点 | `risk_score >= 40` | 提升优先级，列出风险节点 |
| R3 | 深调用链 | 间接节点且 depth >= 2 | 提醒验证层间契约 |
| R4 | 边界风险 | 边界节点 risk > 0 | 标记无法完全检查的外部依赖 |
| R5 | 缺失错误处理 | 有 IO 操作但无异常处理关键词 | 提醒检查异常路径 |
| R6 | 任务类型聚焦 | entrypoint/module/config | 添加对应的审查关注点 |
| R7 | 跳过平凡任务 | file_review + low 优先级 + <3 节点 | 跳过 LLM 调用，节省成本 |

规则是可加的——多条规则可以同时触发，`should_skip` 仅由 R7 产生。

---

## LLM Prompt 策略

### 分层组装

用户 prompt 按层级组装，控制 token 预算：

| 层级 | 内容 | 条件 |
|------|------|------|
| Tier 1 | 任务元数据 + 规则标志 + 图摘要 + 目标源码 | 始终包含 |
| Tier 2 | 直接 callee 的源码 | 图节点 <= 15 时 |
| Tier 3 | caller 源码 + 高风险间接节点 | token 预算允许时 |
| Tier 4 | 反馈循环中的额外请求上下文 | 按需 |

### 输出格式

LLM 必须返回严格的 JSON：

```json
{
    "has_issue": true,
    "confidence": 0.85,
    "findings": [
        {
            "title": "问题标题",
            "description": "详细描述",
            "severity": "critical|high|medium|low|info",
            "file_path": "app/api/auth.py",
            "start_line": 7,
            "end_line": 10,
            "evidence": "引用相关代码",
            "suggestion": "修复建议"
        }
    ]
}
```

解析策略（按优先级）：
1. 直接 `json.loads`
2. 从 ` ```json ``` ` 代码块中提取
3. 查找第一个 `{` 到最后一个 `}`

---

## 快速开始

### 1. 安装依赖

```bash
cd func-logic-agent
pip install -r requirements.txt
```

### 2. 启动 context 服务

```bash
cd ../ai-code-review-context
pip install -r requirements.txt
python -m uvicorn repo_context.api.app:app --host 127.0.0.1 --port 8000
```

### 3. 运行 Agent

```python
import asyncio
from func_logic_agent import FuncLogicAgent, AgentConfig

async def main():
    config = AgentConfig(
        repo_id="sample",
        context_api_base="http://127.0.0.1:8000",
        # 切换到 OpenAI：取消下面的注释
        # llm_provider="openai",
        # llm_model="gpt-4o",
        # openai_api_key="sk-xxx",
    )
    agent = FuncLogicAgent(config)
    results = await agent.run(
        "../ai-code-review-context/tests/fixtures/sample_repo"
    )
    for r in results:
        print(f"{r.task_id}: {r.status} | {r.feedback_message}")

asyncio.run(main())
```

### 4. 验证

```bash
# 检查覆盖率（function_logic 维度的 context_usage 应有记录）
curl http://127.0.0.1:8000/demo/sample/coverage
```

### 5. 运行测试（无需启动服务）

```bash
python -m pytest tests/ -v
```

---

## 对未来 Agent 的接入建议

如果你要基于此框架构建新的审查维度 Agent（如 `security`、`coding_style`），建议：

1. **复制目录结构**，修改 `rule_engine.py` 中的规则和 `prompts.py` 中的系统 prompt
2. **复用 `ContextAPIClient`**，它与审查维度无关
3. **复用 `Orchestrator` 的循环逻辑**，只替换规则和 LLM 调用
4. **修改 `review_dimension` 过滤条件**，让 Agent 只处理自己的维度
5. **每个 Agent 独立部署**，通过不同的 `agent_name` 区分反馈来源

这样多个维度的 Agent 可以并行运行，互不干扰，各自通过 `task-feedback` 提交结果。
