"""
Agent 对话服务
负责会话创建/校验、历史读取与消息持久化。
"""
from __future__ import annotations

from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.database import Conversation, Message


class AgentService:
    """Agent 业务服务层。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_conversation_title(user_message: str) -> str:
        """根据用户首条消息生成会话标题，避免标题过长。"""
        normalized = " ".join(user_message.strip().split())
        if not normalized:
            return "新会话"
        return normalized[:30] + ("..." if len(normalized) > 30 else "")

    async def get_or_create_conversation(
        self,
        user_id: int,
        conversation_id: Optional[int],
        user_message: str,
    ) -> Conversation:
        """
        获取或创建会话。

        - 当传入 conversation_id 时：校验归属，若不存在则抛错。
        - 当未传入 conversation_id 时：自动创建一个新的 agent 会话。
        """
        if conversation_id is not None:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                raise ValueError("会话不存在或无权访问")
            return conversation

        conversation = Conversation(
            user_id=user_id,
            title=self._build_conversation_title(user_message),
            agent_type="agent",
            model_name=settings.DEFAULT_MODEL,
            status="active",
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        logger.info("✅ 自动创建 Agent 会话: id={}, user_id={}", conversation.id, user_id)
        return conversation

    async def get_recent_history(
        self,
        conversation_id: int,
        limit: int = 20,
    ) -> List[Dict[str, str]]:
        """读取会话最近 N 条消息，用于构建上下文。"""
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return [{"role": m.role, "content": m.content} for m in messages]

    async def save_agent_turn(
        self,
        conversation_id: int,
        user_message: str,
        assistant_message: str,
        latency_ms: Optional[int] = None,
        agent_name: Optional[str] = None,
    ) -> None:
        """
        保存一轮 Agent 对话（用户消息 + 助手消息），并更新会话计数。
        """
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            content_type="text",
        )
        self.db.add(user_msg)

        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_message,
            content_type="text",
            model_name=settings.DEFAULT_MODEL,
            latency_ms=latency_ms,
            agent_name=agent_name,
        )
        self.db.add(assistant_msg)

        conversation_result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = conversation_result.scalar_one_or_none()
        if conversation is not None:
            conversation.message_count += 2

        await self.db.commit()
        logger.debug("💾 Agent 对话已保存: conversation_id={}", conversation_id)


__all__ = ["AgentService"]
