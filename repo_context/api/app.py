from fastapi import FastAPI


app = FastAPI(title="AI Code Review Context")


@app.get("/health")
def health() -> dict[str, str]:
    """最小健康检查接口，用于验证阶段 0 API 骨架可启动。"""
    return {"status": "ok"}
