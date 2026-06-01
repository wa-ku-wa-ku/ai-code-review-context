from fastapi.testclient import TestClient

from repo_context.api.app import app


def test_health_endpoint_returns_ok() -> None:
    """确认最小 FastAPI app 暴露健康检查接口。"""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
