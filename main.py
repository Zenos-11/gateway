"""
AI Smart Gateway 主应用入口
基于 FastAPI + LangGraph 的企业级 AI 应用网关
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import setup_logger, logger
from app.infrastructure.database import init_db, close_db
from app.infrastructure.redis import init_redis, close_redis
from app.middleware.logging import LoggingMiddleware
from app.middleware.error_handler import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    general_exception_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化资源，关闭时清理资源
    """
    # 启动时执行
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    logger.info("=" * 60)

    # 初始化日志系统
    setup_logger()

    # 初始化数据库
    try:
        await init_db()
        logger.info("✅ 数据库初始化成功")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise

    # 初始化 Redis
    try:
        await init_redis()
        logger.info("✅ Redis 初始化成功")
    except Exception as e:
        logger.error(f"❌ Redis 初始化失败: {e}")
        raise

    logger.info("=" * 60)
    logger.info(f"✅ {settings.APP_NAME} 启动完成！")
    logger.info(f"📍 API 文档: http://localhost:8000/docs")
    logger.info(f"🏥 健康检查: http://localhost:8000/health")
    logger.info("=" * 60)

    yield

    # 关闭时执行
    logger.info("⏳ 正在关闭应用...")

    # 关闭数据库连接
    await close_db()
    logger.info("✅ 数据库连接已关闭")

    # 关闭 Redis 连接
    await close_redis()
    logger.info("✅ Redis 连接已关闭")

    logger.info("👋 应用已安全退出")


# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.APP_NAME,
    description="基于 FastAPI + LangGraph 的企业级 AI 应用网关",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ===== 配置 CORS 中间件 =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# ===== 添加自定义中间件 =====
app.add_middleware(LoggingMiddleware)

# ===== 注册异常处理器 =====
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# ===== 注册路由 =====
# 注意：路由将在后续步骤中添加
# from app.api.v1 import auth, documents, rag, agents, conversations
# app.include_router(auth.router, prefix="/api/v1", tags=["认证"])
# app.include_router(documents.router, prefix="/api/v1", tags=["文档管理"])
# app.include_router(rag.router, prefix="/api/v1", tags=["RAG问答"])
# app.include_router(agents.router, prefix="/api/v1", tags=["多Agent协作"])
# app.include_router(conversations.router, prefix="/api/v1", tags=["对话管理"])


# ===== 基础端点 =====
@app.get("/", tags=["基础"])
async def root():
    """根路径"""
    return {
        "success": True,
        "data": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "description": "基于 FastAPI + LangGraph 的企业级 AI 应用网关",
            "docs_url": "/docs",
            "health_url": "/health"
        }
    }


@app.get("/health", tags=["基础"])
async def health_check():
    """健康检查端点"""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "debug": settings.DEBUG
        }
    }


@app.get("/system/info", tags=["基础"])
async def system_info():
    """系统信息端点"""
    return {
        "success": True,
        "data": {
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "debug": settings.DEBUG,
            "default_model": settings.DEFAULT_MODEL,
            "features": {
                "rag": True,
                "multi_agent": True,
                "streaming": True,
            }
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )

