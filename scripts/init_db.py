"""
数据库初始化脚本
创建所有数据库表结构
"""
import asyncio
import sys
from pathlib import Path

# 兼容直接执行 python scripts/init_db.py 的场景。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logger import setup_logger, logger
from app.core.security import get_password_hash
from app.infrastructure.database import init_db, get_db_session
from app.models.database import User


async def create_test_user() -> None:
    """创建测试用户"""
    async with get_db_session() as db:
        # 检查是否已存在测试用户
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.username == "testuser")
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            logger.info("测试用户已存在，跳过创建")
            return

        # 创建测试用户
        test_user = User(
            username="testuser",
            email="test@example.com",
            password_hash=get_password_hash("testpass123"),
            role="admin",
            quota_limit=10000,
            is_active=True,
        )

        db.add(test_user)
        await db.commit()

        logger.info("✅ 测试用户创建成功")
        logger.info("   用户名: testuser")
        logger.info("   密码: testpass123")
        logger.info("   邮箱: test@example.com")


async def main() -> None:
    """主函数"""
    setup_logger()

    logger.info("=" * 60)
    logger.info("🔧 开始初始化数据库...")
    logger.info("=" * 60)

    try:
        # 初始化数据库表结构
        await init_db()
        logger.info("✅ 数据库表结构创建成功")

        # 创建测试用户
        await create_test_user()

        logger.info("=" * 60)
        logger.info("🎉 数据库初始化完成！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
