"""
请求日志中间件
记录所有 HTTP 请求的详细信息，包括请求方法、路径、状态码、响应时间等
"""
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import logger
from app.core.config import settings


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        处理请求并记录日志

        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理器

        Returns:
            响应对象
        """
        start_time = time.time()

        # 记录请求信息
        request_id = request.headers.get("X-Request-ID", "unknown")
        client_ip = self._get_client_ip(request)

        logger.info(
            f"请求开始: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": client_ip,
                "user_agent": request.headers.get("user-agent"),
            }
        )

        # 处理请求
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = (time.time() - start_time) * 1000  # 转换为毫秒

            # 记录响应信息
            logger.info(
                f"请求完成: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time_ms": round(process_time, 2),
                }
            )

            # 添加响应头
            response.headers["X-Process-Time"] = str(round(process_time, 2))
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # 记录异常
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"请求失败: {request.method} {request.url.path} - {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "process_time_ms": round(process_time, 2),
                    "error": str(e),
                }
            )
            raise

    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端真实 IP

        Args:
            request: 请求对象

        Returns:
            客户端 IP 地址
        """
        # 检查代理头
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For 可能包含多个 IP，取第一个
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 返回直连 IP
        if request.client:
            return request.client.host

        return "unknown"


__all__ = ["LoggingMiddleware"]
