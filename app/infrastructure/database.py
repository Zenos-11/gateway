"""
数据库连接管理
提供异步数据库连接池、会话管理和生命周期管理
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.core.logger import logger


# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # 调试模式下打印 SQL
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # 连接健康检查
    pool_use_lifo=True,  # 使用 LIFO 队列，减少连接创建
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后不过期对象，避免延迟加载问题
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话（依赖注入）

    Yields:
        AsyncSession: 异步数据库会话

    Example:
        ```python
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
        ```
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库会话错误: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库
    创建所有表结构（仅用于开发环境，生产环境应使用 Alembic 迁移）
    """
    from app.models.database import Base

    async with engine.begin() as conn:
        # 导入所有模型，确保它们被注册到 Base.metadata
        from app.models.database import (
            User, Document, DocumentChunk, Conversation,
            Message, AgentExecution, RetrievalHistory, ApiLog
        )

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表结构初始化完成")


async def close_db() -> None:
    """
    关闭数据库连接
    应用关闭时调用
    """
    await engine.dispose()
    logger.info("数据库连接池已关闭")


def get_db_session() -> AsyncSession:
    """
    获取数据库会话（非依赖注入方式）
    用于在非 FastAPI 上下文中使用

    Returns:
        AsyncSession: 异步数据库会话

    Example:
        ```python
        async def some_function():
            async with get_db_session() as db:
                result = await db.execute(select(User))
                return result.scalars().all()
        ```
    """
    return async_session_maker()


__all__ = [
    "engine",
    "async_session_maker",
    "get_db",
    "get_db_session",
    "init_db",
    "close_db",
]
