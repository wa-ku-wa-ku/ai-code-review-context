# 阶段 6：评审任务生成

## 当前任务

现在只完成阶段 6：评审任务生成。

注意：任务生成不调用 LLM，只基于规则和代码索引。

不要实现最终代码漏洞判断。

## 阶段目标

基于代码图谱自动生成 repo_summary、review_tasks、task_card，并实现 task_id 驱动的 get_related_context。

## 任务说明

这里的“任务”不是开发任务，而是系统生成给评审 Agent 的“代码评审任务卡”。

它告诉 Agent：

```text
审什么；
从哪个节点开始审；
重点关注哪些风险；
推荐查看哪些相关节点和文件。
```

## 需要实现

### 1. repo_summary

内容包括：

```text
repo_id
framework
python_files
entrypoints
test_files
config_files
main_packages
```

### 2. entrypoint_review

每个 API 入口生成一个任务。

例如：

```text
POST /login -> task_route_login
```

### 3. config_review

为配置文件生成任务，例如：

```text
config.py
settings.py
database.py
security.py
.env.example
```

### 4. module_review

为重要目录生成模块任务，例如：

```text
services
repositories
utils
models
schemas
core
```

### 5. task_card

每个任务至少包含：

```text
task_id
repo_id
task_type
target
seed_node_id
priority
review_focus
related_files
status
```

### 6. get_related_context(task_id)

根据任务推荐应该看的节点和文件。

注意：不默认返回大段源码，只返回推荐目标。

## review_focus 规则示例

认证相关：

```text
输入校验
身份认证
密码校验
Token 生成与过期
认证绕过风险
异常处理
```

上传相关：

```text
文件类型校验
文件大小限制
路径穿越风险
恶意文件上传
权限控制
```

配置相关：

```text
敏感信息泄露
DEBUG 配置
数据库连接配置
Token / Secret 配置
跨域 CORS 配置
```

## 测试要求

请补充 pytest：

1. sample_repo 能生成 repo_summary；
2. `POST /login` 能生成 entrypoint_review；
3. `config.py` 能生成 config_review；
4. services 目录能生成 module_review；
5. get_related_context(task_id) 能返回 seed_node_id、recommended_nodes、related_files；
6. 任务生成过程不调用 LLM。

## 验收标准

1. 能生成 repo_summary；
2. 能生成 review_tasks；
3. 每个 route 至少对应一个 entrypoint_review；
4. task_card 字段完整；
5. get_related_context 能根据 task_id 返回推荐上下文；
6. pytest 通过。
