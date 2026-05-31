# 阶段 3：SQLite 索引存储

## 当前任务

现在只完成阶段 3：SQLite 索引存储。

不要实现评审任务生成、覆盖率追踪和 Agent API。

## 阶段目标

把文件、节点、关系存入 SQLite，形成可查询的上下文索引库。

## 需要实现

### 1. `store/schema.sql`

第一版核心表：

```text
code_files
code_nodes
code_edges
review_tasks
context_usage
```

其中 `review_tasks` 和 `context_usage` 可以先建表预留，不要求完整业务逻辑。

### 2. `store/models.py`

定义数据模型：

```text
CodeFile
CodeNode
CodeEdge
ReviewTask
ContextUsage
```

### 3. `store/sqlite_store.py`

封装数据库操作：

- 初始化数据库；
- 插入 code_files；
- 插入 code_nodes；
- 插入 code_edges；
- 按 repo_id 查询；
- 按 node_id 查询节点。

### 4. `index/index_builder.py`

串联阶段 1 和阶段 2：

```text
扫描文件 → AST 解析 → 写入 SQLite
```

## 测试要求

请补充 pytest：

1. SQLite 能初始化；
2. 能写入并查询 CodeFile；
3. 能写入并查询 CodeNode；
4. 不同 repo_id 数据隔离；
5. build_index(sample_repo) 后能查到 login 节点。

## 验收标准

1. 运行 `build_index(repo_id, sample_repo)` 能生成 SQLite 文件；
2. 能查到 `app/api/auth.py`；
3. 能查到 `login` 函数；
4. 能查到 `UserService.authenticate` 方法；
5. pytest 通过。
