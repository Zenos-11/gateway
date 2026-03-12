"""
会话管理 API 路由
提供多轮对话会话的增删查操作

会话（Conversation）是消息（Message）的容器，
同一个 conversation_id 下的所有消息构成一段完整的对话历史。
支持 RAG 会话和 Agent 会话两种类型。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.api.deps import require_current_user, User
from app.models.database import Conversation, Message
from app.models.schemas import ConversationCreate, ConversationResponse, MessageResponse
from app.core.logger import logger

router = APIRouter()


@router.post("/conversations", summary="创建新会话", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新的对话会话

    - **title**: 可选，会话备注标题（如不填则自动生成）
    - **agent_type**: rag（知识库问答）或 agent（多 Agent 协作）
    """
    # 若未提供标题，自动生成以便用户识别
    title = payload.title or f"新会话 #{current_user.id}"

    conversation = Conversation(
        user_id=current_user.id,
        title=title,
        agent_type=payload.agent_type,
        model_name=payload.model_name,
        status="active",
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info(f"✅ 用户 {current_user.id} 创建会话 ID={conversation.id}")
    return conversation


@router.get("/conversations", summary="获取会话列表")
async def list_conversations(
    agent_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的所有会话，支持按类型过滤和分页
    """
    query = (
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )

    if agent_type:
        query = query.where(Conversation.agent_type == agent_type)

    query = query.limit(page_size).offset((page - 1) * page_size)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": c.id,
                    "title": c.title,
                    "agent_type": c.agent_type,
                    "model_name": c.model_name,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "status": c.status,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                }
                for c in conversations
            ],
            "pagination": {"page": page, "page_size": page_size},
        },
    }


@router.get("/conversations/{conversation_id}", summary="获取会话详情及消息历史")
async def get_conversation(
    conversation_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定会话的详情，及其分页消息历史
    """
    # 验证会话归属（权限隔离）
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或无权访问",
        )

    # 分页获取消息历史
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())  # 按时间升序，便于前端渲染对话流
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    messages = msg_result.scalars().all()

    return {
        "success": True,
        "data": {
            "conversation": {
                "id": conversation.id,
                "title": conversation.title,
                "agent_type": conversation.agent_type,
                "model_name": conversation.model_name,
                "message_count": conversation.message_count,
                "total_tokens": conversation.total_tokens,
                "status": conversation.status,
                "created_at": conversation.created_at.isoformat(),
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "model_name": m.model_name,
                    "total_tokens": m.total_tokens,
                    "latency_ms": m.latency_ms,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
            "pagination": {"page": page, "page_size": page_size},
        },
    }


@router.delete("/conversations/{conversation_id}", summary="删除会话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除指定会话及其所有消息（级联删除）
    只有会话所有者才能执行此操作
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或无权访问",
        )

    await db.delete(conversation)
    await db.commit()

    logger.info(f"✅ 会话已删除: ID={conversation_id}, 用户={current_user.id}")
    return {"success": True, "message": "会话已删除"}
