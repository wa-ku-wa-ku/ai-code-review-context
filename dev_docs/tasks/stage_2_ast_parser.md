# 阶段 2：Python AST 符号解析

## 当前任务

现在只完成阶段 2：Python AST 符号解析。

不要实现 SQLite 存储、任务生成、FastAPI API、覆盖率追踪。

## 阶段目标

从 Python 文件中抽取函数、类、方法、import、decorator、签名和行号。

## 需要实现

### 1. `parser/ast_parser.py`

- 使用 Python 标准库 `ast`；
- 解析 Python 源码；
- 语法错误时不能让整个流程崩溃，应返回错误信息。

### 2. 抽取 CodeNode

节点类型包括：

```text
module
class
function
method
```

每个 CodeNode 至少包含：

```text
node_id
type
name
qualified_name
file_path
start_line
end_line
signature
decorators
```

### 3. 抽取 import 信息

支持：

```python
import os
import x.y
from x.y import z
```

### 4. 抽取 decorator 信息

支持：

```python
@router.post("/login")
@app.get("/health")
@some_decorator
```

## 测试要求

请补充 pytest：

1. 能识别 `def login`；
2. 能识别 `class UserService`；
3. 能识别 `UserService.authenticate` 方法；
4. 能识别 import；
5. 能识别 decorator；
6. 语法错误文件不会导致测试崩溃。

## 验收标准

1. 输入 `sample_repo/app/api/auth.py`；
2. 能输出 login 函数节点；
3. 能输出 UserService 类和 authenticate 方法节点；
4. 节点包含正确行号和签名；
5. pytest 通过。
