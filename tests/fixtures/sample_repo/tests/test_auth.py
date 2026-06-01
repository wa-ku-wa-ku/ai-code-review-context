from pathlib import Path


def test_sample_auth_file_declares_login_route() -> None:
    """fixture 自带的最小测试：只验证示例路由源码存在。"""
    sample_root = Path(__file__).resolve().parents[1]
    auth_source = (sample_root / "app" / "api" / "auth.py").read_text(
        encoding="utf-8"
    )

    assert '@router.post("/login")' in auth_source
