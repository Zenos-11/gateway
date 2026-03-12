"""
安全模块
提供密码加密、JWT 令牌生成和验证、用户认证等功能
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logger import logger


# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def parse_user_id_claim(user_id_value: Any) -> Optional[int]:
    """
    将 JWT 中的用户 ID claim 规范化为整数。

    Args:
        user_id_value: JWT 中的用户 ID 原始值

    Returns:
        转换后的整数用户 ID，无法转换时返回 None
    """
    if user_id_value is None or isinstance(user_id_value, bool):
        return None

    if isinstance(user_id_value, int):
        return user_id_value

    if isinstance(user_id_value, str):
        normalized_value = user_id_value.strip()
        if not normalized_value:
            return None

        try:
            return int(normalized_value)
        except ValueError:
            logger.warning(f"JWT 用户 ID 格式无效: {user_id_value}")
            return None

    logger.warning(f"JWT 用户 ID 类型无效: {type(user_id_value).__name__}")
    return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码

    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    获取密码哈希

    Args:
        password: 明文密码

    Returns:
        哈希后的密码
    """
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建访问令牌

    Args:
        data: 要编码的数据（通常包含 user_id 和 username）
        expires_delta: 过期时间增量

    Returns:
        JWT 访问令牌
    """
    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    # 编码 JWT
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    创建刷新令牌

    Args:
        data: 要编码的数据

    Returns:
        JWT 刷新令牌
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码 JWT 令牌

    Args:
        token: JWT 令牌

    Returns:
        解码后的数据，失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT 解码失败: {e}")
        return None


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    验证 JWT 令牌

    Args:
        token: JWT 令牌
        token_type: 令牌类型（access 或 refresh）

    Returns:
        验证成功返回 payload，失败返回 None
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # 检查令牌类型
    if payload.get("type") != token_type:
        logger.warning(f"令牌类型不匹配，期望: {token_type}, 实际: {payload.get('type')}")
        return None

    return payload


def extract_user_id_from_token(token: str) -> Optional[int]:
    """
    从 JWT 令牌中提取用户 ID

    Args:
        token: JWT 令牌

    Returns:
        用户 ID，失败返回 None
    """
    payload = verify_token(token)
    if payload is None:
        return None

    return parse_user_id_claim(payload.get("sub") or payload.get("user_id"))


class TokenData:
    """令牌数据模型"""
    user_id: Optional[int] = None
    username: Optional[str] = None
    exp: Optional[datetime] = None
    type: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TokenData":
        """
        从 JWT payload 创建 TokenData

        Args:
            payload: JWT payload

        Returns:
            TokenData 实例
        """
        return cls(
            user_id=parse_user_id_claim(payload.get("sub") or payload.get("user_id")),
            username=payload.get("username"),
            exp=datetime.fromtimestamp(payload.get("exp", 0)) if payload.get("exp") else None,
            type=payload.get("type")
        )


__all__ = [
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
    "parse_user_id_claim",
    "extract_user_id_from_token",
    "TokenData",
]
