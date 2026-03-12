"""
认证 API 路由
提供用户注册、登录等功能
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.services.auth_service import AuthService
from app.api.deps import require_current_user, User
from app.core.security import verify_token, create_access_token
from app.core.config import settings
from app.core.logger import logger
from datetime import timedelta

router = APIRouter()


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., description="密码")


class RefreshRequest(BaseModel):
    """Token 刷新请求"""
    refresh_token: str = Field(..., description="刷新令牌")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    email: str
    role: str
    quota_used: int
    quota_limit: int


class AuthResponse(BaseModel):
    """认证响应"""
    user: UserResponse
    tokens: Dict[str, Any]


# ===== API 端点 =====
@router.post("/auth/register", summary="用户注册", response_model=AuthResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    注册新用户

    - **username**: 用户名（3-50字符）
    - **email**: 邮箱地址
    - **password**: 密码（至少6字符）
    """
    try:
        auth_service = AuthService(db)
        user = await auth_service.register(
            username=request.username,
            email=request.email,
            password=request.password,
        )

        # 注册后自动登录
        login_data = await auth_service.login(
            email=request.email,
            password=request.password,
        )

        return login_data

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ 注册失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败，请稍后重试"
        )


@router.post("/auth/login", summary="用户登录", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    用户登录

    - **email**: 邮箱地址
    - **password**: 密码

    返回访问令牌和刷新令牌
    """
    try:
        auth_service = AuthService(db)
        login_data = await auth_service.login(
            email=request.email,
            password=request.password,
        )

        return login_data

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"❌ 登录失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败，请稍后重试"
        )


@router.get("/auth/me", summary="获取当前用户", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(require_current_user),
):
    """
    获取当前登录用户的信息，需要携带有效的 Bearer Token。
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        quota_used=current_user.quota_used,
        quota_limit=current_user.quota_limit,
    )


@router.post("/auth/refresh", summary="刷新访问令牌")
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    使用 refresh_token 换取新的 access_token。
    refresh_token 本身不会刷新，过期后用户需重新登录。
    """
    payload = verify_token(request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少用户信息",
        )

    # 验证用户是否仍然有效（防止已被禁用的用户刷新 Token）
    auth_service = AuthService(db)
    user = await auth_service.get_current_user(int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    new_access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "success": True,
        "data": {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
    }


@router.post("/auth/logout", summary="用户登出")
async def logout():
    """
    用户登出

    注意：由于使用 JWT 无状态认证，客户端只需删除 Token 即可
    """
    return {
        "success": True,
        "message": "登出成功"
    }
