"""
多 Agent 协作 API 路由
提供 HTTP 和 WebSocket 两种访问方式

- POST /agents/chat         → 同步聊天（等待最终结果）
- POST /agents/chat/stream  → SSE 流式聊天（逐步推送节点事件）
- WebSocket /agents/ws      → 双向实时通信
- GET  /agents/status       → 获取 Agent 图状态信息
"""
import json
import time
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.api.deps import require_current_user, User
from app.agents.graph import run_agent, run_agent_stream
from app.services.agent_service import AgentService
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

def _validate_mode(mode: str) -> str:
    """校验并规范化 mode 参数。"""
    normalized_mode = mode.strip().lower()
    valid_modes = {"auto", "rag", "code", "general"}
    if normalized_mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"非法 mode: {mode}，仅支持: {', '.join(sorted(valid_modes))}",
        )
    return normalized_mode


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
    mode = _validate_mode(request.mode)
    agent_service = AgentService(db)

    try:
        conversation = await agent_service.get_or_create_conversation(
            user_id=current_user.id,
            conversation_id=request.conversation_id,
            user_message=request.message,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )

    history = await agent_service.get_recent_history(conversation.id)
    start_time = time.perf_counter()

    try:
        final_answer = await run_agent(
            user_message=request.message,
            conversation_history=history,
            user_id=current_user.id,
            mode=mode,
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        await agent_service.save_agent_turn(
            conversation_id=conversation.id,
            user_message=request.message,
            assistant_message=final_answer,
            latency_ms=latency_ms,
            agent_name="agent_graph",
        )
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
            "conversation_id": conversation.id,
            "mode": mode,
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
    - `routing`: Supervisor 决定的目标 Agent
    - `token`: 子 Agent 输出的文本片段（token 级实时推送）
    - `done`: 全部完成
    - `error`: 处理出错
    """
    mode = _validate_mode(request.mode)
    agent_service = AgentService(db)

    try:
        conversation = await agent_service.get_or_create_conversation(
            user_id=current_user.id,
            conversation_id=request.conversation_id,
            user_message=request.message,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )

    history = await agent_service.get_recent_history(conversation.id)

    async def _generate():
        # 先返回会话元信息，方便前端绑定 conversation_id
        meta_event = {
            "type": "meta",
            "agent": "system",
            "content": "",
            "conversation_id": conversation.id,
            "mode": mode,
        }
        yield f"data: {json.dumps(meta_event, ensure_ascii=False)}\n\n"

        start_time = time.perf_counter()
        answer_parts: List[str] = []
        final_agent_name = "agent_graph"
        has_error = False
        done_event: Dict[str, Any] | None = None

        try:
            async for event in run_agent_stream(
                request.message,
                history,
                user_id=current_user.id,
                mode=mode,
            ):
                if event.get("type") == "token":
                    token_text = event.get("content", "")
                    if token_text:
                        answer_parts.append(token_text)
                    if event.get("agent"):
                        final_agent_name = str(event["agent"])

                if event.get("type") == "error":
                    has_error = True

                if event.get("type") == "done":
                    # 先暂存 done，待消息持久化成功后再发送
                    done_event = event
                    continue

                # event 已经是 {"type", "agent", "content"} 格式，直接序列化推送
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            # 仅在本轮成功时持久化，避免把失败请求写成完整回答
            final_answer = "".join(answer_parts).strip()
            if (not has_error) and final_answer:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                await agent_service.save_agent_turn(
                    conversation_id=conversation.id,
                    user_message=request.message,
                    assistant_message=final_answer,
                    latency_ms=latency_ms,
                    agent_name=final_agent_name,
                )

            # 持久化完成后再发送 done（若上游未显式发送则补一个）
            done_payload = done_event or {"type": "done", "agent": "system", "content": ""}
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"❌ Agent SSE 失败: {e}")
            err = json.dumps({"type": "error", "agent": "system", "content": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

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

        from app.core.security import parse_user_id_claim, verify_token
        payload = verify_token(token)
        if not payload:
            await websocket.send_json({"type": "error", "content": "令牌无效或已过期"})
            await websocket.close(code=4001)
            return

        user_id = parse_user_id_claim(payload.get("sub") or payload.get("user_id"))
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
                mode = _validate_mode(msg_data.get("mode", "auto"))

                if not user_message:
                    continue

                agent_service = AgentService(db)
                conversation = await agent_service.get_or_create_conversation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                )
                history = await agent_service.get_recent_history(conversation.id)

                answer_parts: List[str] = []
                final_agent_name = "agent_graph"
                has_error = False
                start_time = time.perf_counter()
                done_event: Dict[str, Any] | None = None

                async for event in run_agent_stream(
                    user_message,
                    history,
                    user_id=user_id,
                    mode=mode,
                ):
                    if event.get("type") == "token":
                        token_text = event.get("content", "")
                        if token_text:
                            answer_parts.append(token_text)
                        if event.get("agent"):
                            final_agent_name = str(event["agent"])

                    if event.get("type") == "error":
                        has_error = True

                    if event.get("type") == "done":
                        done_event = event
                        continue

                    await websocket.send_json(event)

                final_answer = "".join(answer_parts).strip()
                if (not has_error) and final_answer:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    await agent_service.save_agent_turn(
                        conversation_id=conversation.id,
                        user_message=user_message,
                        assistant_message=final_answer,
                        latency_ms=latency_ms,
                        agent_name=final_agent_name,
                    )

                await websocket.send_json(done_event or {"type": "done", "agent": "system", "content": ""})

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket 断开: user_id={user_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "消息格式错误，请发送 JSON"})
            except ValueError as error:
                await websocket.send_json({"type": "error", "content": str(error)})
            except HTTPException as error:
                await websocket.send_json({"type": "error", "content": str(error.detail)})
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
