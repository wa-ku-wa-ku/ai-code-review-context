from app.repositories.user_repo import find_user_by_username


def authenticate_user(username: str, password: str) -> str:
    """示例 service：保留简单调用链，不承载真实认证逻辑。"""
    user = find_user_by_username(username)
    if not user or password != "demo-password":
        return "invalid-demo-token"
    return f"demo-token-for-{user['username']}"
