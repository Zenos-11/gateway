"""
Redis 连接管理
提供 Redis 连接池和常用操作封装
"""
import json
from typing import Optional, Any, List

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logger import logger


# 创建 Redis 连接池
redis_pool: ConnectionPool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    decode_responses=True,  # 自动解码为字符串
    encoding="utf-8",
)


async def get_redis() -> Redis:
    """
    获取 Redis 客户端（依赖注入）

    Returns:
        Redis: 异步 Redis 客户端

    Example:
        ```python
        @app.get("/cache")
        async def get_cache(redis: Redis = Depends(get_redis)):
            value = await redis.get("key")
            return {"value": value}
        ```
    """
    return aioredis.Redis(connection_pool=redis_pool)


async def init_redis() -> None:
    """初始化 Redis 连接"""
    try:
        redis = aioredis.Redis(connection_pool=redis_pool)
        await redis.ping()
        logger.info("Redis 连接成功")
        await redis.close()
    except Exception as e:
        logger.error(f"Redis 连接失败: {e}")
        raise


async def close_redis() -> None:
    """关闭 Redis 连接池"""
    await redis_pool.disconnect()
    logger.info("Redis 连接池已关闭")


class RedisCache:
    """Redis 缓存操作封装"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str) -> Optional[str]:
        """
        获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回 None
        """
        try:
            value = await self.redis.get(key)
            return value
        except Exception as e:
            logger.error(f"Redis GET 失败: {e}")
            return None

    async def set(
        self,
        key: str,
        value: str,
        expire: Optional[int] = None
    ) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒），None 表示不过期

        Returns:
            是否设置成功
        """
        try:
            await self.redis.set(key, value, ex=expire)
            return True
        except Exception as e:
            logger.error(f"Redis SET 失败: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE 失败: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        检查键是否存在

        Args:
            key: 缓存键

        Returns:
            键是否存在
        """
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS 失败: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置过期时间

        Args:
            key: 缓存键
            seconds: 过期秒数

        Returns:
            是否设置成功
        """
        try:
            await self.redis.expire(key, seconds)
            return True
        except Exception as e:
            logger.error(f"Redis EXPIRE 失败: {e}")
            return False

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        递增

        Args:
            key: 缓存键
            amount: 递增量

        Returns:
            递增后的值，失败返回 None
        """
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR 失败: {e}")
            return None

    async def get_json(self, key: str) -> Optional[Any]:
        """
        获取 JSON 缓存

        Args:
            key: 缓存键

        Returns:
            解码后的 Python 对象，不存在返回 None
        """
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"JSON 解码失败: {key}")
            return None

    async def set_json(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """
        设置 JSON 缓存

        Args:
            key: 缓存键
            value: Python 对象（需可 JSON 序列化）
            expire: 过期时间（秒）

        Returns:
            是否设置成功
        """
        try:
            json_value = json.dumps(value, ensure_ascii=False)
            return await self.set(key, json_value, expire)
        except Exception as e:
            logger.error(f"JSON 编码失败: {e}")
            return False

    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        """
        批量获取

        Args:
            keys: 缓存键列表

        Returns:
            缓存值列表
        """
        try:
            return await self.redis.mget(keys)
        except Exception as e:
            logger.error(f"Redis MGET 失败: {e}")
            return [None] * len(keys)

    async def mset(self, mapping: dict) -> bool:
        """
        批量设置

        Args:
            mapping: 键值对字典

        Returns:
            是否设置成功
        """
        try:
            await self.redis.mset(mapping)
            return True
        except Exception as e:
            logger.error(f"Redis MSET 失败: {e}")
            return False


# 限流操作
class RedisRateLimiter:
    """Redis 限流器"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window: int
    ) -> bool:
        """
        检查是否允许访问（滑动窗口算法）

        Args:
            key: 限流键（如 "rate_limit:user_123:api/v1/chat"）
            limit: 限制次数
            window: 时间窗口（秒）

        Returns:
            是否允许访问
        """
        try:
            current = await self.redis.incr(key)
            if current == 1:
                # 第一次访问，设置过期时间
                await self.redis.expire(key, window)
            return current <= limit
        except Exception as e:
            logger.error(f"限流检查失败: {e}")
            return True  # 失败时默认允许


__all__ = [
    "redis_pool",
    "get_redis",
    "init_redis",
    "close_redis",
    "RedisCache",
    "RedisRateLimiter",
]
