from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from langchain_core.messages import HumanMessage
from app.agents.graph import agent_graph

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应模型"""
    response: str
    session_id: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    智能体聊天接口

    接收用户消息，通过 LangGraph 处理后返回响应
    """
    try:
        # 构造初始状态
        initial_state = {
            "messages": [HumanMessage(content=request.message)]
        }

        # 运行智能体图
        result = agent_graph.invoke(initial_state)

        # 提取响应消息
        response_message = result["messages"][-1].content if result["messages"] else "处理完成"

        return ChatResponse(
            response=response_message,
            session_id=request.session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/agents/status")
async def get_agent_status():
    """获取智能体状态"""
    return {
        "status": "active",
        "type": "LangGraph Agent",
        "version": "1.0.0"
    }
