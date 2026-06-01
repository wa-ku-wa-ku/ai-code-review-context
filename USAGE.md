# 使用说明：仓库上下文处理 Demo

本文说明当前 demo 版本中，用户如何提供代码仓库、系统如何读取文件，以及如何跑完整的索引、任务生成、上下文查询和覆盖率追踪流程。

## 当前能力边界

当前项目已经实现的是后端上下文处理模块，不是完整 Web 产品。

已有能力：

- 读取本地 Python 仓库目录；
- 安全解压 zip 包到指定目录；
- 扫描有效 Python 文件；
- 解析 AST 符号、import、decorator、调用关系和路由；
- 构建 SQLite 索引；
- 生成规则化评审任务；
- 提供上下文查询工具；
- 记录工具使用情况并生成覆盖率报告。

当前没有实现：

- 文件上传接口；
- 前端页面；
- 最终漏洞判断；
- 多 Agent 调度；
- 完整 MCP Server。

也就是说，当前 demo 的“上传文件”不是通过浏览器上传，而是把仓库目录或 zip 文件放到后端机器可访问的位置，然后由 Python 代码读取。

## 用户如何提供文件

### 方式一：提供本地仓库目录

用户把待评审的 Python 仓库放在某个目录，例如：

```text
D:\demo_repos\my_python_repo
```

系统通过 `repo_context.ingest.repo_loader.load_repo_path()` 校验路径是否存在、是否为目录。

后续 `build_index()` 会扫描这个目录：

```python
from repo_context.index.index_builder import build_index

build_index(
    repo_id="my-repo",
    repo_path=r"D:\demo_repos\my_python_repo",
    db_path=r"D:\demo_output\context.db",
)
```

### 方式二：提供 zip 文件

用户也可以提供 zip 包，例如：

```text
D:\uploads\my_python_repo.zip
```

系统先调用 `extract_zip()` 解压到指定目录：

```python
from repo_context.ingest.zip_loader import extract_zip
from repo_context.index.index_builder import build_index

repo_dir = extract_zip(
    zip_path=r"D:\uploads\my_python_repo.zip",
    output_dir=r"D:\workspaces\my_python_repo",
)

build_index(
    repo_id="my-repo",
    repo_path=repo_dir,
    db_path=r"D:\demo_output\context.db",
)
```

zip 解压会检查路径穿越，例如 `../../evil.py` 会被拒绝，避免写出目标目录。

## 系统如何读取文件

整体流程如下：

```text
本地目录或 zip
    ↓
repo_loader / zip_loader
    ↓
file_scanner 扫描 Python 文件
    ↓
ast_parser 解析符号
    ↓
call_graph 识别调用关系和路由
    ↓
sqlite_store 写入 SQLite
    ↓
ContextService / ReviewTaskGenerator / CoverageService 查询和生成结果
```

扫描阶段会跳过这些目录：

```text
.git
.venv
venv
__pycache__
dist
build
site-packages
node_modules
```

每个 Python 文件会记录：

```text
file_path
file_type
language
line_count
is_test
```

AST 解析失败不会中断整个仓库处理。语法错误文件会被记录为文件，但不会产生符号节点，其他正常文件继续入库。

## 最小端到端示例

以下示例使用项目自带的 sample repo：

```powershell
.\.venv\Scripts\python.exe
```

进入 Python 后执行：

```python
from pathlib import Path

from repo_context.index.index_builder import build_index
from repo_context.service.context_service import ContextService
from repo_context.service.coverage_service import CoverageService
from repo_context.task.review_task_generator import ReviewTaskGenerator

repo_id = "sample-repo"
repo_path = Path("tests/fixtures/sample_repo")
db_path = Path("demo_context.db")

# 1. 构建 SQLite 索引
build_index(repo_id=repo_id, repo_path=repo_path, db_path=db_path)

# 2. 创建上下文服务
context_service = ContextService(
    repo_id=repo_id,
    repo_root=repo_path,
    db_path=db_path,
)

# 3. 搜索符号
matches = context_service.search_symbol("login")
login = next(item for item in matches if item["qualified_name"] == "app.api.auth.login")

# 4. 查看节点详情和源码，同时记录 context_usage
detail = context_service.get_node_detail(
    login["node_id"],
    include_source=True,
    task_id="manual-demo",
)

# 5. 生成评审任务
task_generator = ReviewTaskGenerator(context_service)
plan = task_generator.generate()

# 6. 根据 task_id 获取推荐上下文，不默认返回源码正文
task_context = task_generator.get_related_context("task_route_post_login")

# 7. 生成覆盖率报告
coverage_service = CoverageService(context_service, task_generator)
coverage_report = coverage_service.get_coverage_report()

print(detail)
print(plan.to_dict())
print(task_context)
print(coverage_report)
```

## 上下文工具怎么用

当前推荐通过 `ContextService` 调用，也可以通过 `repo_context.tools` 下的薄封装函数调用。

常用工具：

```text
search_symbol
get_node_detail
get_file_snippet
get_callees
get_callers
trace_call_chain
explore_related_symbols
get_related_context
```

示例：

```python
from repo_context.tools import get_callees, get_file_snippet, search_symbol

matches = search_symbol(context_service, "login")
login_node_id = matches[0]["node_id"]

callees = get_callees(context_service, login_node_id)

snippet = get_file_snippet(
    context_service,
    file_path="app/api/auth.py",
    start_line=1,
    end_line=20,
    task_id="task_route_post_login",
)
```

`get_file_snippet()` 会阻止读取仓库外路径，例如 `../AGENTS.md` 会报错。

## 输出结果有哪些

### SQLite 索引

索引库中包含：

```text
code_files
code_nodes
code_edges
review_tasks
context_usage
```

其中当前主要使用：

- `code_files`: 文件信息；
- `code_nodes`: module、class、function、method、route 节点；
- `code_edges`: contains、calls、maps_to 边；
- `context_usage`: 工具实际访问过的节点和文件。

### 评审任务

`ReviewTaskGenerator.generate()` 输出：

```text
repo_summary
review_tasks
coverage_report
```

任务类型包括：

```text
entrypoint_review
config_review
module_review
file_review
```

阶段 7 还可以基于实际使用覆盖率生成：

```text
uncovered_file_review
```

## 如果要做一个简单前端

可以做，但当前后端还没有上传 API，需要先补很薄的一层 FastAPI 接口。

建议最小前端流程：

```text
1. 用户上传 zip 或填写服务器上的仓库路径
2. 后端解压或读取目录
3. 后端调用 build_index
4. 前端展示 repo_summary 和 review_tasks
5. 用户点击 task_card
6. 前端调用 get_related_context(task_id)
7. 用户查看推荐节点、文件和必要源码片段
8. 后端记录 context_usage
9. 前端展示 coverage_report
```

建议最小后端 API：

```text
POST /repos/upload
POST /repos/index
GET  /repos/{repo_id}/summary
GET  /repos/{repo_id}/tasks
GET  /repos/{repo_id}/tasks/{task_id}/context
GET  /repos/{repo_id}/nodes/{node_id}
GET  /repos/{repo_id}/files/snippet
GET  /repos/{repo_id}/coverage
```

如果只做 demo 前端，可以先不做复杂权限和任务状态流转，重点展示：

- 上传 zip；
- 构建索引；
- 任务列表；
- 任务详情；
- 推荐上下文；
- 覆盖率报告。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前项目测试覆盖了从文件扫描、AST 解析、SQLite 索引、调用关系、上下文工具、任务生成到覆盖率验收的主流程。
