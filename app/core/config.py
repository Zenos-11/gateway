"""
核心配置模块
使用 Pydantic Settings 管理环境变量，支持类型验证和默认值
"""
from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    # ===== 应用基础配置 =====
    APP_NAME: str = Field(default="AI Smart Gateway", description="应用名称")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")
    SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production",
        description="JWT 加密密钥"
    )

    # ===== 数据库配置 =====
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_smart_gateway",
        description="数据库连接字符串"
    )
    DB_POOL_SIZE: int = Field(default=20, description="数据库连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=40, description="数据库最大溢出连接数")
    DB_POOL_RECYCLE: int = Field(default=3600, description="连接回收时间（秒）")

    # ===== Redis 配置 =====
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis 连接字符串"
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Redis 最大连接数")

    # ===== 向量数据库配置 =====
    CHROMA_HOST: str = Field(default="localhost", description="ChromaDB 主机")
    CHROMA_PORT: int = Field(default=8001, description="ChromaDB 端口")
    CHROMA_EMBEDDING_MODEL_URL: str = Field(
        default="https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz",
        description="Chroma 默认 embedding 模型下载地址"
    )
    CHROMA_EMBEDDING_CACHE_DIR: str = Field(
        default="~/.cache/chroma/onnx_models/all-MiniLM-L6-v2",
        description="Chroma embedding 模型缓存目录"
    )
    CHROMA_EMBEDDING_DOWNLOAD_TIMEOUT_SECONDS: int = Field(
        default=1800,
        description="Chroma embedding 模型下载超时时间（秒）"
    )

    # ===== OpenAI API 配置 =====
    OPENAI_API_KEY: str = Field(default="sk-4d6e671585284c19b12a2fa9eba546b3", description="OpenAI API Key")
    OPENAI_API_BASE: str = Field(
        default="https://api.deepseek.com",
        description="DEEPSEEK API Base URL"
    )
    DEFAULT_MODEL: str = Field(default="deepseek-chat", description="默认模型")
    DEFAULT_TEMPERATURE: float = Field(default=0.7, description="默认温度")
    DEFAULT_MAX_TOKENS: int = Field(default=2000, description="默认最大 Token 数")

    # ===== JWT 配置 =====
    JWT_SECRET_KEY: str = Field(
        default="your-jwt-secret-key-change-this",
        description="JWT 密钥"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT 算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="访问令牌过期时间（分钟）")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="刷新令牌过期时间（天）")

    # ===== 限流配置 =====
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="是否启用限流")
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, description="每分钟请求限制")

    # ===== 文件上传配置 =====
    MAX_FILE_SIZE: int = Field(default=10485760, description="最大文件大小（字节，默认10MB）")
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=["pdf", "txt", "md", "docx"],
        description="允许的文件类型"
    )
    UPLOAD_DIR: str = Field(default="uploads", description="文件上传目录")

    # ===== CORS 配置 =====
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="允许的 CORS 来源"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="允许携带凭证")
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"], description="允许的 HTTP 方法")
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"], description="允许的 HTTP 头")

    # ===== 日志配置 =====
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    LOG_FILE: str = Field(default="logs/app.log", description="日志文件路径")

    # ===== 用户配额配置 =====
    DEFAULT_QUOTA_LIMIT: int = Field(default=1000, description="默认用户配额限制")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("ALLOWED_FILE_TYPES", mode="before")
    @classmethod
    def parse_file_types(cls, v):
        """解析文件类型配置"""
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """解析 CORS 配置"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    使用 lru_cache 确保配置只加载一次
    """
    return Settings()


# 全局配置实例
settings = get_settings()
