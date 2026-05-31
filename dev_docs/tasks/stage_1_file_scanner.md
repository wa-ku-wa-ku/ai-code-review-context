# 阶段 1：仓库输入与文件扫描

## 当前任务

现在只完成阶段 1：仓库输入与文件扫描。

不要实现 AST 解析、SQLite 存储、调用关系、任务生成和 Agent 工具接口。

## 阶段目标

输入一个 Python 仓库路径或 zip 文件后，系统能安全读取仓库，并扫描出有效文件。

## 需要实现

### 1. `ingest/repo_loader.py`

- 支持本地仓库路径读取；
- 路径不存在时返回明确错误。

### 2. `ingest/zip_loader.py`

- 支持 zip 解压；
- 必须防止路径穿越，例如 `../../evil.py`；
- 解压到指定目录。

### 3. `ingest/file_filter.py`

跳过以下目录：

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

### 4. `ingest/file_scanner.py`

- 扫描仓库文件；
- 识别 `.py` 文件；
- 识别 `source / test / config / other`；
- 统计 `line_count`；
- 返回结构化 `CodeFile` 对象或字典。

## 数据字段

每个文件至少包含：

```text
file_path
file_type
language
line_count
is_test
```

## 测试要求

请补充 pytest：

1. 测试正常仓库扫描；
2. 测试 `.venv / __pycache__ / .git` 被过滤；
3. 测试 `config.py` 被识别为 config；
4. 测试 `tests/test_xxx.py` 被识别为 test；
5. 测试 zip 路径穿越被拒绝或跳过。

## 验收标准

1. 输入 `tests/fixtures/sample_repo` 能扫描出有效 Python 文件；
2. 无关目录不会进入结果；
3. 文件类型识别正确；
4. pytest 通过；
5. 不实现 AST 解析和数据库功能。

## 完成后请输出

1. 修改文件列表；
2. 核心实现说明；
3. 测试命令；
4. 测试结果；
5. 后续阶段建议。
