from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # API 配置
    OPENAI_API_KEY: str
    OPENAI_API_BASE: Optional[str] = "https://api.openai.com/v1"

    # 应用配置
    APP_NAME: str = "AI Smart Gateway"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 模型配置
    DEFAULT_MODEL: str = "gpt-3.5-turbo"
    DEFAULT_TEMPERATURE: float = 0.7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# 全局配置实例
settings = Settings()
