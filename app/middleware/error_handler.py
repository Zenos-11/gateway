"""
异常处理中间件
统一处理应用中的各类异常，返回标准化的错误响应
"""
from typing import Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.logger import logger


class AppException(Exception):
    """应用异常基类"""

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Union[dict, list] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class ValidationError(AppException):
    """参数验证错误"""

    def __init__(self, message: str, details: Union[dict, list] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class UnauthorizedError(AppException):
    """未授权错误"""

    def __init__(self, message: str = "未授权访问"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class ForbiddenError(AppException):
    """禁止访问错误"""

    def __init__(self, message: str = "无权限访问"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN
        )


class NotFoundError(AppException):
    """资源不存在错误"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND
        )


class RateLimitError(AppException):
    """速率限制错误"""

    def __init__(self, message: str = "请求过于频繁，请稍后再试"):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )


class QuotaExceededError(AppException):
    """配额超限错误"""

    def __init__(self, message: str = "配额已用完"):
        super().__init__(
            message=message,
            code="QUOTA_EXCEEDED",
            status_code=status.HTTP_403_FORBIDDEN
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    处理应用自定义异常

    Args:
        request: 请求对象
        exc: 应用异常

    Returns:
        JSON 错误响应
    """
    logger.error(
        f"应用异常: {exc.code} - {exc.message}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "details": exc.details
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    处理请求验证异常

    Args:
        request: 请求对象
        exc: 验证异常

    Returns:
        JSON 错误响应
    """
    logger.warning(
        f"请求验证失败: {request.url.path}",
        extra={"errors": exc.errors()}
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数验证失败",
                "details": exc.errors()
            }
        }
    )


async def sqlalchemy_exception_handler(
    request: Request,
    exc: SQLAlchemyError
) -> JSONResponse:
    """
    处理数据库异常

    Args:
        request: 请求对象
        exc: 数据库异常

    Returns:
        JSON 错误响应
    """
    logger.error(
        f"数据库异常: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method
        }
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "DATABASE_ERROR",
                "message": "数据库操作失败",
                "details": None
            }
        }
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理通用异常

    Args:
        request: 请求对象
        exc: 异常对象

    Returns:
        JSON 错误响应
    """
    logger.error(
        f"未捕获的异常: {type(exc).__name__} - {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method
        },
        exc_info=True
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "details": None
            }
        }
    )


__all__ = [
    "AppException",
    "ValidationError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "QuotaExceededError",
    "app_exception_handler",
    "validation_exception_handler",
    "sqlalchemy_exception_handler",
    "general_exception_handler",
]
