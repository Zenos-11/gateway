"""
认证服务
处理用户注册、登录、Token 生成等
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
)
from app.core.config import settings
from app.core.logger import logger


class AuthService:
    """认证服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """
        用户注册

        Args:
            username: 用户名
            email: 邮箱
            password: 密码

        Returns:
            创建的用户对象

        Raises:
            ValueError: 用户名或邮箱已存在
        """
        # 检查用户名是否存在
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none():
            raise ValueError(f"用户名 '{username}' 已存在")

        # 检查邮箱是否存在
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            raise ValueError(f"邮箱 '{email}' 已被注册")

        # 创建用户
        user = User(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            role="user",
            quota_limit=settings.DEFAULT_QUOTA_LIMIT,
            quota_used=0,
            is_active=True,
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"✅ 新用户注册成功: {username} ({email})")
        return user

    async def login(
        self,
        email: str,
        password: str,
    ) -> Dict[str, Any]:
        """
        用户登录

        Args:
            email: 邮箱
            password: 密码

        Returns:
            包含用户信息和 Token 的字典

        Raises:
            ValueError: 邮箱或密码错误
        """
        # 查找用户
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        # 验证用户
        if not user:
            raise ValueError("邮箱或密码错误")
        if not user.is_active:
            raise ValueError("用户已被禁用")

        # 验证密码
        if not verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误")

        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        # 生成 Token
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )

        logger.info(f"✅ 用户登录成功: {user.username}")

        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "quota_used": user.quota_used,
                "quota_limit": user.quota_limit,
            },
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            }
        }

    async def get_current_user(
        self,
        user_id: int,
    ) -> Optional[User]:
        """
        根据 ID 获取当前用户

        Args:
            user_id: 用户 ID

        Returns:
            用户对象，不存在返回 None
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_quota(
        self,
        user_id: int,
        tokens_used: int,
    ) -> None:
        """
        更新用户配额

        Args:
            user_id: 用户 ID
            tokens_used: 使用的 Token 数量
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.quota_used += tokens_used
            await self.db.commit()


__all__ = ["AuthService"]
