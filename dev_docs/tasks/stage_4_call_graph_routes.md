# 阶段 4：调用关系与路由识别

## 当前任务

现在只完成阶段 4：调用关系与路由识别。

不要实现评审任务生成和覆盖率追踪。

## 阶段目标

在代码图谱中建立调用关系，识别 FastAPI / Flask API 入口点。

## 需要实现

### 1. 基础 calls 边抽取

从 AST 中识别函数调用，例如：

```python
authenticate()
service.authenticate()
UserService().authenticate()
```

无法精确解析时，也要保留原始调用名或 unresolved 信息。

### 2. import + 名称解析基础版

结合 import 信息，把常见调用尽量映射到真实 CodeNode。

例如：

```python
from app.services.user_service import UserService
UserService().authenticate()
```

尽量解析为：

```text
app.services.user_service.UserService.authenticate
```

### 3. FastAPI 路由识别

支持：

```python
@router.get("/users")
@router.post("/login")
@app.get("/health")
```

生成 route 节点，并建立 route -> handler 关系。

### 4. Flask 路由识别

支持：

```python
@app.route("/login", methods=["POST"])
def login():
    pass
```

## 测试要求

请补充 pytest：

1. `login` 能识别到调用 `authenticate`；
2. `authenticate` 能识别到调用 `find_by_username`；
3. 能识别 `POST /login` FastAPI 路由；
4. route 能关联 handler 函数；
5. 无法解析的调用不会导致异常。

## 验收标准

1. sample_repo 中 `POST /login` 被识别为 route；
2. route 能关联到 `login` 函数；
3. `login` 能查到下游调用 `authenticate`；
4. `authenticate` 能查到下游调用 `find_by_username`；
5. pytest 通过。
