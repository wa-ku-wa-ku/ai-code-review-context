from app.repositories.user_repo import find_user_by_username


class UserService:
    """示例 service 类，用于阶段 2 验证类和方法解析。"""

    def authenticate(self, username: str, password: str) -> str:
        """示例认证方法，保留简单调用链供后续阶段使用。"""
        user = find_user_by_username(username)
        if not user or password != "demo-password":
            return "invalid-demo-token"
        return f"demo-token-for-{user['username']}"


def authenticate_user(username: str, password: str) -> str:
    """兼容阶段 0 fixture 的函数入口。"""
    return UserService().authenticate(username=username, password=password)
