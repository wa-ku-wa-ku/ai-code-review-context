# 阶段 5：上下文工具接口

## 当前任务

现在只完成阶段 5：上下文工具接口。

不要实现覆盖率追踪、最终评审判断和完整 MCP Server。

## 阶段目标

把索引能力封装成 Agent 可调用的工具接口。

## 需要实现

建议创建：

```text
tools/symbol_tools.py
tools/graph_tools.py
tools/context_tools.py
tools/file_tools.py
service/context_service.py
```

### 工具接口

第一版实现：

```text
search_symbol
get_node_detail
get_file_snippet
get_callees
get_callers
trace_call_chain
explore_related_symbols
```

`get_related_context` 可以先做基础版，后续阶段 6 再接入 task_id。

## 各工具要求

### search_symbol

按关键字搜索函数、类、方法、路由。

返回字段：

```text
node_id
type
name
qualified_name
file_path
start_line
end_line
```

### get_node_detail

根据 node_id 获取节点详情和源码。

参数：

```text
include_source: bool
```

### get_file_snippet

根据文件路径和行号范围读取源码片段。

必须防止读取仓库外路径。

### get_callees / get_callers

查询调用关系，支持 depth 和 limit。

### trace_call_chain

查询两个节点之间是否存在调用路径。

### explore_related_symbols

围绕某个节点返回相关节点和边，可控制是否包含源码。

## 测试要求

请补充 pytest：

1. 搜索 login 能返回 login 函数；
2. get_node_detail(login) 能返回源码；
3. get_file_snippet 能返回指定行源码；
4. get_callees(login) 能返回 authenticate；
5. get_callers(authenticate) 能返回 login；
6. trace_call_chain(login, find_by_username) 能返回路径；
7. 所有返回结果都是 JSON serializable。

## 验收标准

1. 通过 ContextService 能调用基础工具；
2. Agent 不需要直接访问 SQLite；
3. 所有工具返回结构稳定；
4. pytest 通过。
