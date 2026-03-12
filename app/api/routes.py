"""
多 Agent 协作 API 路由
提供 HTTP 和 WebSocket 两种访问方式

- POST /agents/chat         → 同步聊天（等待最终结果）
- POST /agents/chat/stream  → SSE 流式聊天（逐步推送节点事件）
- WebSocket /agents/ws      → 双向实时通信
- GET  /agents/status       → 获取 Agent 图状态信息
"""
import json
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.api.deps import require_current_user, User
from app.agents.graph import run_agent_stream
from app.models.database import Conversation, Message
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()


# ===== 请求/响应模型 =====

class AgentChatRequest(BaseModel):
    """Agent 对话请求体"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=2000)
    conversation_id: Optional[int] = Field(None, description="会话 ID（可选，用于多轮记忆）")
    mode: str = Field(
        "auto",
        description="路由模式: auto=自动判断 | rag=知识库检索 | code=代码任务 | general=通用",
    )


# ===== 辅助函数 =====

async def _get_conversation_history(
    conversation_id: Optional[int],
    user_id: int,
    db: AsyncSession,
) -> List[Dict[str, str]]:
    """
    查询会话历史消息，返回 [{role, content}] 列表。
    验证会话归属以防越权访问。
    """
    if not conversation_id:
        return []

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not conv_result.scalar_one_or_none():
        return []

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .limit(20)  # 最近 20 条，控制上下文长度
    )
    messages = msg_result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


# ===== HTTP 端点 =====

@router.post("/agents/chat", summary="Agent 同步对话")
async def agents_chat(
    request: AgentChatRequest,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    向多 Agent 系统发起一轮对话，等待所有节点完成后返回最终结果。
    消息经 Supervisor 路由到对应的子 Agent（RAG / 代码 / 通用）。
    """
    history = await _get_conversation_history(
        request.conversation_id, current_user.id, db
    )

    final_answer = ""
    agent_events = []

    try:
        async for event in run_agent_stream(request.message, history):
            for node_name, node_state in event.items():
                new_messages = node_state.get("messages", [])
                for msg in reversed(new_messages):
                    if hasattr(msg, "content") and msg.content:
                        final_answer = msg.content
                        break
                agent_events.append({
                    "node": node_name,
                    "message_count": len(new_messages),
                })

    except Exception as e:
        logger.error(f"❌ Agent 对话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent 对话失败: {str(e)}",
        )

    return {
        "success": True,
        "data": {
            "answer": final_answer,
            "agent_trace": agent_events,
        },
    }


@router.post("/agents/chat/stream", summary="Agent 流式对话（SSE）")
async def agents_chat_stream(
    request: AgentChatRequest,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent 流式对话端点（Server-Sent Events）

    每推进一个节点，立即推送一个 SSE 事件：
    - `thinking`: Supervisor 路由决策
    - `token`: 子 Agent 输出的文本片段
    - `done`: 全部完成
    - `error`: 处理出错
    """
    history = await _get_conversation_history(
        request.conversation_id, current_user.id, db
    )

    async def _generate():
        try:
            async for event in run_agent_stream(request.message, history):
                for node_name, node_state in event.items():
                    event_type = "thinking" if node_name == "supervisor" else "token"
                    new_messages = node_state.get("messages", [])

                    for msg in new_messages:
                        if hasattr(msg, "content") and msg.content:
                            payload = json.dumps(
                                {"type": event_type, "agent": node_name, "content": msg.content},
                                ensure_ascii=False,
                            )
                            yield f"data: {payload}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'agent': 'system', 'content': ''}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"❌ Agent SSE 失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'agent': 'system', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===== WebSocket 端点 =====

@router.websocket("/agents/ws")
async def agents_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket 双向实时通信端点

    客户端消息格式（JSON）：
    ```json
    {"token": "<JWT>", "message": "...", "conversation_id": null}
    ```
    服务端推送格式：
    ```json
    {"type": "thinking|token|done|error", "agent": "...", "content": "..."}
    ```
    通过 JWT 鉴权，拒绝所有未认证连接。
    """
    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        data = json.loads(raw)
        token = data.get("token", "")

        if not token:
            await websocket.send_json({"type": "error", "content": "未提供认证令牌"})
            await websocket.close(code=4001)
            return

        from app.core.security import verify_token
        payload = verify_token(token)
        if not payload:
            await websocket.send_json({"type": "error", "content": "令牌无效或已过期"})
            await websocket.close(code=4001)
            return

        user_id: int = payload.get("sub") or payload.get("user_id")
        if not user_id:
            await websocket.send_json({"type": "error", "content": "令牌中缺少用户信息"})
            await websocket.close(code=4001)
            return

        logger.info(f"🔌 WebSocket 连接建立: user_id={user_id}")
        await websocket.send_json({"type": "connected", "content": "连接成功"})

        while True:
            try:
                text = await websocket.receive_text()
                msg_data = json.loads(text)
                user_message = msg_data.get("message", "").strip()
                conversation_id = msg_data.get("conversation_id")

                if not user_message:
                    continue

                history = await _get_conversation_history(conversation_id, user_id, db)

                async for event in run_agent_stream(user_message, history):
                    for node_name, node_state in event.items():
                        for msg in node_state.get("messages", []):
                            if hasattr(msg, "content") and msg.content:
                                await websocket.send_json({
                                    "type": "token",
                                    "agent": node_name,
                                    "content": msg.content,
                                })

                await websocket.send_json({"type": "done", "agent": "system", "content": ""})

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket 断开: user_id={user_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "消息格式错误，请发送 JSON"})
            except Exception as e:
                logger.error(f"❌ WebSocket 处理失败: {e}")
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"❌ WebSocket 连接异常: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@router.get("/agents/status", summary="获取 Agent 状态")
async def get_agent_status(
    current_user: User = Depends(require_current_user),
):
    """返回 Agent 图拓扑结构和可用节点信息"""
    return {
        "success": True,
        "data": {
            "graph_nodes": ["supervisor", "rag_agent", "code_agent", "general_agent"],
            "routing": {
                "supervisor": ["rag_agent", "code_agent", "general_agent"],
                "rag_agent": ["__end__"],
                "code_agent": ["__end__"],
                "general_agent": ["__end__"],
            },
            "available_tools": {
                "rag_agent": ["rag_search"],
                "code_agent": ["format_code"],
                "general_agent": ["get_current_datetime"],
            },
            "model": settings.DEFAULT_MODEL,
        },
    }
