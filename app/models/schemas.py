"""
Pydantic 数据模型定义
用于 API 请求/响应的数据校验与序列化
严格遵守类型注解，防止运行时类型错误
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ===== 通用响应结构 =====

class BaseResponse(BaseModel):
    """统一响应包装器"""
    success: bool = True
    message: str = "操作成功"


# ===== 文档相关 =====

class DocumentResponse(BaseModel):
    """文档摘要信息（用于列表）"""
    id: int
    filename: str
    file_type: str
    file_size: Optional[int] = None
    chunk_count: int = 0
    processing_status: str
    title: Optional[str] = None
    created_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """文档详情（含额外字段）"""
    vector_count: int = 0
    indexing_time_ms: Optional[int] = None


class DocumentChunkResponse(BaseModel):
    """文档块信息"""
    id: int
    chunk_index: int
    content: str
    embedding_status: str
    token_count: Optional[int] = None


# ===== 会话相关 =====

class ConversationCreate(BaseModel):
    """创建会话请求体"""
    title: Optional[str] = Field(None, description="会话标题", max_length=200)
    agent_type: str = Field("rag", description="会话类型: rag / agent / general")
    model_name: Optional[str] = Field(None, description="使用的模型名称")


class ConversationResponse(BaseModel):
    """会话摘要"""
    id: int
    title: Optional[str] = None
    agent_type: str
    model_name: Optional[str] = None
    message_count: int = 0
    total_tokens: int = 0
    status: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """单条消息"""
    id: int
    role: str
    content: str
    model_name: Optional[str] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime


# ===== RAG 相关 =====

class RAGQueryRequest(BaseModel):
    """RAG 查询请求体"""
    query: str = Field(..., description="查询问题", min_length=1, max_length=1000)
    conversation_id: Optional[int] = Field(None, description="会话 ID（多轮对话）")
    top_k: int = Field(5, description="检索文档块数量", ge=1, le=20)
    score_threshold: Optional[float] = Field(
        None,
        description="向量距离阈值(越小越严格，建议 1.2-1.8；不传则不过滤)",
        ge=0.0,
    )
    model: Optional[str] = Field(None, description="使用的模型")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)


class RAGSource(BaseModel):
    """RAG 来源文档"""
    content: str
    metadata: Dict[str, Any] = {}
    score: float = 0.0


class RAGQueryResponse(BaseModel):
    """RAG 查询响应体"""
    answer: str
    sources: List[RAGSource]
    confidence: float
    performance: Dict[str, int]
    tokens_used: Optional[Dict[str, int]] = None


# ===== Agent 相关 =====

class AgentChatRequest(BaseModel):
    """Agent 对话请求体"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=2000)
    conversation_id: Optional[int] = Field(None, description="会话 ID（多轮记忆）")
    mode: str = Field(
        "auto",
        description="路由模式: auto=自动判断 | rag=知识库检索 | code=代码任务 | general=通用问答",
    )
    user_id: Optional[int] = Field(None, description="用户 ID（WebSocket 场景由服务端注入）")


class AgentStreamEvent(BaseModel):
    """Agent 流式事件（WebSocket / SSE）"""
    event_type: str = Field(
        ..., description="事件类型: thinking | tool_call | token | result | error | done"
    )
    agent: str = Field(..., description="产生事件的 Agent 名称")
    content: str
    metadata: Dict[str, Any] = {}


__all__ = [
    "BaseResponse",
    "DocumentResponse",
    "DocumentDetailResponse",
    "DocumentChunkResponse",
    "ConversationCreate",
    "ConversationResponse",
    "MessageResponse",
    "RAGQueryRequest",
    "RAGSource",
    "RAGQueryResponse",
    "AgentChatRequest",
    "AgentStreamEvent",
]
