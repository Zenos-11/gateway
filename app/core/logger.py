"""
日志配置模块
使用 loguru 实现结构化日志，支持文件轮转和请求追踪
"""
import sys
from pathlib import Path
from loguru import logger

from app.core.config import settings


def setup_logger() -> None:
    """
    配置日志系统
    - 移除默认的处理器
    - 添加控制台输出（带颜色）
    - 添加文件输出（支持轮转）
    - 添加请求追踪支持
    """
    # 移除默认处理器
    logger.remove()

    # 添加控制台处理器
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=settings.LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # 创建日志目录
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # 添加文件处理器（普通日志）
    logger.add(
        settings.LOG_FILE,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        level=settings.LOG_LEVEL,
        rotation="00:00",  # 每天午夜轮转
        retention="30 days",  # 保留30天
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # 添加错误日志文件（单独记录错误）
    error_log_file = log_dir / "error.log"
    logger.add(
        str(error_log_file),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        level="ERROR",
        rotation="00:00",
        retention="90 days",  # 错误日志保留更久
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"日志系统初始化完成 | 级别: {settings.LOG_LEVEL} | 文件: {settings.LOG_FILE}")


def get_logger(name: str = None):
    """
    获取 logger 实例

    Args:
        name: logger 名称，默认使用调用模块的名称

    Returns:
        logger 实例
    """
    if name:
        return logger.bind(name=name)
    return logger


# 导出 logger 实例
__all__ = ["logger", "setup_logger", "get_logger"]
