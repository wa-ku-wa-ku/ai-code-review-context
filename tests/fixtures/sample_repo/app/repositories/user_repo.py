def find_by_username(username: str) -> dict[str, str] | None:
    """示例 repository：返回固定用户，供后续解析调用关系使用。"""
    if username == "demo":
        return {"username": "demo"}
    return None


def find_user_by_username(username: str) -> dict[str, str] | None:
    """兼容旧 fixture 名称。"""
    return find_by_username(username)
