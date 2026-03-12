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
from app.core.logger import logger

router = APIRouter()


async def _mock_current_user() -> None:
    """临时依赖：返回未认证状态。"""
    return None


# ===== 请求/响应模型 =====
class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., description="密码")


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
async def get_current_user(
    current_user: Any = Depends(_mock_current_user),
):
    """
    获取当前登录用户的信息

    注意：此接口需要认证（待实现）
    """
    if current_user is None:
        # 临时返回测试用户
        return UserResponse(
            id=1,
            username="testuser",
            email="test@example.com",
            role="admin",
            quota_used=0,
            quota_limit=10000,
        )
    return current_user


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
