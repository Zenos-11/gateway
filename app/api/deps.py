"""
依赖注入模块
提供 FastAPI 依赖注入函数，用于获取数据库会话、Redis、当前用户等
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.infrastructure.redis import get_redis
from app.core.security import verify_token, parse_user_id_claim
from app.core.logger import logger
from app.models.database import User


# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[int]:
    """
    获取当前用户 ID（从 JWT 令牌中）

    Args:
        credentials: HTTP Bearer 凭证

    Returns:
        用户 ID，未认证返回 None

    Raises:
        HTTPException: 令牌无效时
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_user_id = payload.get("sub") or payload.get("user_id")
    user_id = parse_user_id_claim(raw_user_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中的用户信息无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: Optional[int] = Depends(get_current_user_id)
) -> Optional[User]:
    """
    获取当前用户（完整对象）

    Args:
        db: 数据库会话
        user_id: 用户 ID

    Returns:
        用户对象，未认证返回 None
    """
    if user_id is None:
        return None

    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )

    return user


async def require_current_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    要求必须认证（返回用户对象，未认证抛出异常）

    Args:
        current_user: 当前用户

    Returns:
        用户对象

    Raises:
        HTTPException: 未认证时
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user


async def get_request_id(
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID")
) -> str:
    """
    获取请求 ID

    Args:
        x_request_id: 请求 ID 头

    Returns:
        请求 ID
    """
    return x_request_id or "unknown"


async def check_quota(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    检查用户配额

    Args:
        current_user: 当前用户

    Returns:
        用户对象

    Raises:
        HTTPException: 配额不足时
    """
    if current_user.quota_used >= current_user.quota_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"配额已用完（{current_user.quota_used}/{current_user.quota_limit}）"
        )

    return current_user


__all__ = [
    "security",
    "get_current_user_id",
    "get_current_user",
    "require_current_user",
    "get_request_id",
    "check_quota",
]
