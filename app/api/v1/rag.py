"""
RAG 问答 API 路由
提供智能问答功能
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.api.deps import require_current_user, User
from app.services.rag_service import RAGService
from app.core.logger import logger

router = APIRouter()


class RAGQueryRequest(BaseModel):
    """RAG 查询请求"""
    query: str = Field(..., description="查询问题", min_length=1, max_length=1000)
    conversation_id: Optional[int] = Field(None, description="会话 ID（用于多轮对话）")
    top_k: int = Field(5, description="检索文档数量", ge=1, le=20)
    score_threshold: Optional[float] = Field(None, description="相似度阈值（0-1）", ge=0, le=1)
    model: Optional[str] = Field(None, description="使用的模型")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0, le=2)


@router.post("/rag/query", summary="RAG 智能问答")
async def rag_query(
    request: RAGQueryRequest,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    基于文档的智能问答

    1. 从向量数据库检索相关文档
    2. 使用 LLM 生成答案
    3. 返回答案和来源引用
    """
    try:
        rag_service = RAGService(db)

        result = await rag_service.query(
            query_text=request.query,
            user_id=current_user.id,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            model=request.model,
            temperature=request.temperature,
        )

        return {
            "success": True,
            "data": {
                "answer": result["answer"],
                "sources": result["sources"],
                "confidence": result["confidence"],
                "performance": {
                    "retrieval_time_ms": result["retrieval_time_ms"],
                    "generation_time_ms": result["generation_time_ms"],
                    "total_time_ms": result["total_time_ms"],
                },
                "tokens_used": result.get("tokens_used"),
            }
        }

    except Exception as e:
        logger.error(f"❌ RAG 查询失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG 查询失败: {str(e)}"
        )


@router.get("/rag/history", summary="获取查询历史")
async def get_rag_history(
    conversation_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取 RAG 查询历史

    如果指定 conversation_id，返回该会话的历史
    否则返回所有会话的历史
    """
    try:
        from sqlalchemy import select
        from app.models.database import Message, Conversation

        # 构建查询
        query = (
            select(Message)
            .join(Conversation)
            .where(Conversation.user_id == current_user.id)
        )

        if conversation_id:
            query = query.where(Message.conversation_id == conversation_id)

        query = query.order_by(Message.created_at.desc())
        query = query.limit(page_size).offset((page - 1) * page_size)

        result = await db.execute(query)
        messages = result.scalars().all()

        # 配对消息（user + assistant）
        paired_messages = []
        i = 0
        while i < len(messages) - 1:
            if messages[i].role == "assistant" and messages[i+1].role == "user":
                # 交换顺序
                user_msg = messages[i+1]
                assistant_msg = messages[i]
            elif messages[i].role == "user":
                user_msg = messages[i]
                assistant_msg = messages[i+1] if i+1 < len(messages) else None
            else:
                i += 1
                continue

            paired_messages.append({
                "query": user_msg.content if user_msg else "",
                "answer": assistant_msg.content if assistant_msg else "",
                "created_at": user_msg.created_at.isoformat() if user_msg else None,
                "latency_ms": assistant_msg.latency_ms if assistant_msg else None,
                "tokens_used": assistant_msg.total_tokens if assistant_msg else None,
            })
            i += 2

        return {
            "success": True,
            "data": {
                "items": paired_messages,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                }
            }
        }

    except Exception as e:
        logger.error(f"❌ 获取查询历史失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取查询历史失败: {str(e)}"
        )
