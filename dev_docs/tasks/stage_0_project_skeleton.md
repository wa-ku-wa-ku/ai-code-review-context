# 阶段 0：工程骨架搭建

## 当前任务

现在只完成阶段 0：工程骨架搭建。

不要实现仓库扫描、AST 解析、SQLite 存储、任务生成和工具接口。

## 阶段目标

完成后项目应该具备：

1. 清晰的 Python 包目录结构；
2. pytest 测试框架；
3. 基础依赖文件；
4. 一个用于后续测试的 sample Python 仓库。

## 建议目录结构

```text
repo_context/
├── ingest/
├── parser/
├── index/
├── store/
├── task/
├── tools/
├── service/
├── api/
└── tests/
```

## 具体要求

1. 创建 `repo_context` 包和子目录；
2. 为每个目录添加必要的 `__init__.py`；
3. 创建 `requirements.txt` 或 `pyproject.toml`；
4. 添加 pytest 基础测试；
5. 创建 `tests/fixtures/sample_repo`，里面包含最小 FastAPI 风格示例：
   - `app/api/auth.py`
   - `app/services/user_service.py`
   - `app/repositories/user_repo.py`
   - `app/config.py`
   - `tests/test_auth.py`
6. sample_repo 中至少包含一个 `@router.post("/login")` 路由函数；
7. 代码和测试中添加必要中文注释。

## 验收标准

1. `pytest` 可以运行；
2. `repo_context` 可以被正常 import；
3. `tests/fixtures/sample_repo` 目录存在；
4. sample_repo 中有 login 路由、service、repository、config 文件；
5. 不实现后续阶段功能。

## 完成后请输出

1. 新增了哪些文件；
2. 每个文件的作用；
3. 如何运行测试；
4. pytest 结果；
5. 是否有未完成事项。
