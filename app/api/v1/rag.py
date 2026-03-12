"""
RAG 问答 API 路由
提供智能问答功能（含流式 SSE 端点）
"""
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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
    score_threshold: Optional[float] = Field(
        None,
        description="向量距离阈值（越小越严格，建议 1.2-1.8；不传则不过滤）",
        ge=0,
    )
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


@router.post("/rag/query/stream", summary="RAG 流式智能问答（SSE）")
async def rag_query_stream(
    request: RAGQueryRequest,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    基于文档的流式智能问答（Server-Sent Events）

    客户端接收 SSE 事件流，事件格式：
    - `sources`: 检索到的来源文档（首先返回）
    - `token`: LLM 逐字输出的文本片段
    - `error`: 发生错误
    - `done`: 流式传输完成

    前端使用方式：
    ```javascript
    const evtSource = new EventSource('/api/v1/rag/query/stream');
    evtSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'token') outputBuffer += data.content;
    };
    ```
    """
    async def _event_generator() -> AsyncGenerator[str, None]:
        try:
            rag_service = RAGService(db)
            async for event_chunk in rag_service.stream_query(
                query_text=request.query,
                user_id=current_user.id,
                conversation_id=request.conversation_id,
                top_k=request.top_k,
                model=request.model,
                temperature=request.temperature,
            ):
                yield event_chunk
        except Exception as e:
            import json
            logger.error(f"❌ RAG 流式查询失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            # 禁用缓存，确保 SSE 实时推送到客户端
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 告知 Nginx 不缓冲 SSE 响应
        },
    )
