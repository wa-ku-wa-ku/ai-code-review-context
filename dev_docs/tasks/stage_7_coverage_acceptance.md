# 阶段 7：覆盖率追踪与整体验收

## 当前任务

现在只完成阶段 7：覆盖率追踪与整体验收。

不要新增无关功能，不要实现最终漏洞判断。

## 阶段目标

记录 Agent 使用过哪些上下文，生成覆盖率报告，完成端到端验收。

## 需要实现

### 1. context_usage 记录

记录工具调用时访问过哪些节点和文件。

字段可以包括：

```text
usage_id
repo_id
task_id
tool_name
node_id
file_path
used_at
```

### 2. get_coverage_report

报告包括：

```text
文件覆盖率
节点覆盖率
任务完成率
未覆盖文件列表
未覆盖入口点列表
```

### 3. uncovered_file_review

为没有被任何任务覆盖的源码文件生成补充任务。

### 4. 端到端测试

模拟真实流程：

```text
输入 sample_repo
构建索引
生成任务
查询工具
记录覆盖率
输出 coverage_report
```

## 测试要求

请补充 pytest：

1. 调用 get_node_detail 会记录 node_id；
2. 调用 get_file_snippet 会记录 file_path；
3. 能统计文件覆盖率；
4. 能统计节点覆盖率；
5. 能列出未覆盖文件；
6. 未覆盖文件能生成 uncovered_file_review；
7. 端到端流程可以一键运行。

## 验收标准

1. 能生成 context_usage 记录；
2. 能生成 coverage_report；
3. 能发现未覆盖文件；
4. 能生成 uncovered_file_review；
5. 端到端测试通过；
6. pytest 通过。
