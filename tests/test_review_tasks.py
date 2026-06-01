import inspect
import json
from pathlib import Path

import pytest

import repo_context.task.review_task_generator as task_generator_module
from repo_context.index.index_builder import build_index
from repo_context.service.context_service import ContextService
from repo_context.task.review_task_generator import ReviewTaskGenerator


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REPO = ROOT / "tests" / "fixtures" / "sample_repo"


def test_sample_repo_generates_repo_summary(task_generator: ReviewTaskGenerator) -> None:
    """sample_repo 能生成 repo_summary。"""
    plan = task_generator.generate()
    summary = plan.repo_summary.to_dict()

    assert summary["repo_id"] == "sample-repo"
    assert summary["framework"] == "fastapi"
    assert summary["python_files"] > 0
    assert summary["entrypoints"]
    assert "tests/test_auth.py" in summary["test_files"]
    assert "app/config.py" in summary["config_files"]
    assert "app" in summary["main_packages"]
    _assert_json_serializable(summary)


def test_post_login_generates_entrypoint_review(
    task_generator: ReviewTaskGenerator,
) -> None:
    """POST /login 应生成入口点评审任务。"""
    tasks = task_generator.generate().review_tasks
    task = next(item for item in tasks if item.target == "POST /login")

    assert task.task_type == "entrypoint_review"
    assert task.task_id == "task_route_post_login"
    assert task.seed_node_id
    assert "身份认证" in task.review_focus
    assert "app/api/auth.py" in task.related_files


def test_config_py_generates_config_review(task_generator: ReviewTaskGenerator) -> None:
    """config.py 应生成配置评审任务。"""
    tasks = task_generator.generate().review_tasks
    task = next(item for item in tasks if item.target == "app/config.py")

    assert task.task_type == "config_review"
    assert task.priority == "medium"
    assert "敏感信息泄露" in task.review_focus
    assert task.related_files == ["app/config.py"]


def test_services_directory_generates_module_review(
    task_generator: ReviewTaskGenerator,
) -> None:
    """services 目录应生成模块评审任务。"""
    tasks = task_generator.generate().review_tasks
    task = next(item for item in tasks if item.target == "app/services")

    assert task.task_type == "module_review"
    assert task.seed_node_id
    assert "app/services/user_service.py" in task.related_files
    assert "异常处理" in task.review_focus


def test_task_card_fields_are_complete(task_generator: ReviewTaskGenerator) -> None:
    """每张 task_card 都应包含阶段 6 要求字段。"""
    required_fields = {
        "task_id",
        "repo_id",
        "task_type",
        "target",
        "seed_node_id",
        "priority",
        "review_focus",
        "related_files",
        "status",
    }

    for task in task_generator.generate().review_tasks:
        assert required_fields.issubset(task.to_dict())
        assert task.status == "pending"


def test_get_related_context_by_task_id(task_generator: ReviewTaskGenerator) -> None:
    """get_related_context(task_id) 应返回推荐节点和文件。"""
    task = next(
        item
        for item in task_generator.generate().review_tasks
        if item.task_id == "task_route_post_login"
    )

    context = task_generator.get_related_context(task.task_id)

    assert context["task_id"] == task.task_id
    assert context["seed_node_id"] == task.seed_node_id
    assert context["recommended_nodes"]
    assert "app/api/auth.py" in context["related_files"]
    _assert_json_serializable(context)


def test_review_task_generation_does_not_call_llm() -> None:
    """任务生成源码不应引用 LLM 或 OpenAI 调用。"""
    source = inspect.getsource(task_generator_module).lower()

    assert "openai" not in source
    assert "llm" not in source
    assert "chatcompletion" not in source


def _assert_json_serializable(value: object) -> None:
    json.dumps(value, ensure_ascii=False)


def _build_task_generator(tmp_path: Path) -> ReviewTaskGenerator:
    db_path = tmp_path / "context.db"
    build_index("sample-repo", SAMPLE_REPO, db_path)
    return ReviewTaskGenerator(
        ContextService(
            repo_id="sample-repo",
            repo_root=SAMPLE_REPO,
            db_path=db_path,
        )
    )


@pytest.fixture()
def task_generator(tmp_path: Path) -> ReviewTaskGenerator:
    return _build_task_generator(tmp_path)
