from fastapi import APIRouter

from app.services.user_service import authenticate, authenticate_user


router = APIRouter()


@router.post("/login")
def login(username: str, password: str) -> dict[str, str]:
    """示例登录接口，仅用于后续阶段的路由识别测试。"""
    token = authenticate(username=username, password=password)
    return {"access_token": token, "token_type": "bearer"}
