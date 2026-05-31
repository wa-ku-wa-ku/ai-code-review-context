# Codex 使用说明

这个文件包用于让 Codex 按阶段实现“上下文处理模块”，避免每次手写长提示词。

## 使用方式

把本文件包中的内容复制到项目仓库根目录，保留以下结构：

```text
AGENTS.md
docs/
tasks/
prompts/
```

推荐每个阶段使用一个 Git 分支：

```bash
git checkout -b stage-1-file-scanner
```

然后对 Codex 输入：

```text
请先阅读 AGENTS.md 和 tasks/stage_1_file_scanner.md。
现在只完成 stage_1_file_scanner.md 中的任务，不要实现后续阶段。
完成后运行 pytest，并按验收标准逐条汇报。
```

## 推荐工作流

```text
1. 新建阶段分支
2. 让 Codex 读取 AGENTS.md + 当前阶段任务文件
3. Codex 实现代码
4. Codex 运行 pytest
5. 人工检查 diff
6. 对照验收清单逐条确认
7. 不通过就让 Codex 修复
8. 通过后 commit
9. 进入下一阶段
```

## 关键原则

- 一次只做一个阶段；
- 不要让 Codex 提前实现后续阶段；
- 不要让 Codex 写漏洞判断逻辑；
- 不要让任务生成依赖 LLM；
- 每个阶段必须有测试；
- 验收通过后再进入下一阶段。

## 自动分支说明

本文件包的 `AGENTS.md` 已加入全局 Git 分支工作规则。以后让 Codex 开始新阶段时，只需要让它读取 `AGENTS.md` 和对应 `tasks/stage_xxx.md`，它应先检查 `git status`，再自动创建或切换对应阶段分支。默认不自动 commit、不自动 push，除非用户明确要求。
