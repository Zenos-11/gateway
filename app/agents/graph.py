"""
多 Agent LangGraph 状态机
实现研究员 / 程序员 / 审查员三个专家 Agent 的协作编排。

核心设计思路（回字形路由）：
    用户消息 → 路由节点（supervisor）
        ↓ 判断意图
      rag_agent          → 知识库检索 + 回答
      code_agent         → 代码生成 / 分析
      general_agent      → 通用 LLM 问答
        ↓ 所有分支最终汇聚
       __end__

状态机中唯一共享的状态是 AgentState，多个节点通过对它的读写来传递信息。
"""
import json
import os
from typing import Annotated, AsyncGenerator, Dict, Sequence, TypedDict

import operator
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.agents.tools import RAG_TOOLS, CODE_TOOLS, UTILITY_TOOLS
from app.core.config import settings
from app.core.logger import logger


# ===== 共享状态定义 =====

class AgentState(TypedDict):
    """
    LangGraph 共享状态
    messages 使用 operator.add 注解，表示每个节点只需返回「新增消息」，
    LangGraph 会自动拼接到历史列表中，不会覆盖。
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # 路由决策：supervisor 填写，后续节点读取
    next_agent: str
    # 当前用户消息原文（方便子 Agent 直接使用）
    user_input: str


# ===== LLM 工厂 =====

def _build_llm(temperature: float = 0.7) -> ChatOpenAI:
    """
    根据配置构建 ChatOpenAI 实例。
    在没有配置 API Key 时降级为 dummy 模式，保证本地可运行。
    """
    return ChatOpenAI(
        model=settings.DEFAULT_MODEL,
        temperature=temperature,
        openai_api_key=settings.OPENAI_API_KEY or "sk-placeholder",
        openai_api_base=settings.OPENAI_API_BASE,
        streaming=True,
    )


# ===== 节点函数定义 =====

async def supervisor_node(state: AgentState) -> Dict:
    """
    路由节点（Supervisor）
    分析用户意图，决定由哪个子 Agent 来处理。
    意图分类：rag_agent / code_agent / general_agent
    """
    user_input = state.get("user_input", "")

    # 简单关键词路由（生产中可换成 LLM 分类器或 ReAct 规划器）
    code_keywords = ["代码", "函数", "程序", "bug", "error", "python", "def ", "class "]
    rag_keywords = ["文档", "知识库", "搜索", "检索", "查找", "资料", "根据", "文件"]

    lower_input = user_input.lower()

    if any(kw in lower_input for kw in code_keywords):
        next_agent = "code_agent"
    elif any(kw in lower_input for kw in rag_keywords):
        next_agent = "rag_agent"
    else:
        next_agent = "general_agent"

    logger.info(f"🧭 Supervisor 路由决策: {next_agent} (输入: {user_input[:50]}...)")

    return {
        "next_agent": next_agent,
        "messages": [
            AIMessage(content=f"[Supervisor] 判断任务类型为: {next_agent}", name="supervisor")
        ],
    }


async def rag_agent_node(state: AgentState) -> Dict:
    """
    RAG 检索专家 Agent
    调用 rag_search 工具检索知识库，再用 LLM 生成基于文档的回答。
    """
    user_input = state.get("user_input", "")
    logger.info(f"📚 RAG Agent 处理: {user_input[:50]}")

    # 调用 rag_search 工具
    search_result = await RAG_TOOLS[0].ainvoke({"query": user_input, "top_k": 5})

    # 构建 RAG 回答提示词
    llm = _build_llm(temperature=0.3)  # RAG 场景温度低一些，确保答案忠实于文档
    system_msg = SystemMessage(
        content=(
            "你是一位专业的知识库检索助手。请仅根据以下检索到的文档内容来回答用户问题，"
            "不要编造不在文档中的信息。如果文档没有相关内容，请如实说明。\n\n"
            f"检索到的文档内容：\n{search_result}"
        )
    )

    try:
        response = await llm.ainvoke([system_msg, HumanMessage(content=user_input)])
        answer = response.content
    except Exception as e:
        logger.error(f"❌ RAG Agent LLM 调用失败: {e}")
        answer = f"RAG 知识库检索已完成，但生成回答时出错：{str(e)}\n\n检索结果：\n{search_result}"

    return {"messages": [AIMessage(content=answer, name="rag_agent")]}


async def code_agent_node(state: AgentState) -> Dict:
    """
    程序员 Agent
    负责代码生成、代码解释、Bug 诊断等任务。
    内置代码格式化调用（不执行任何外部命令，确保安全）。
    """
    user_input = state.get("user_input", "")
    logger.info(f"💻 Code Agent 处理: {user_input[:50]}")

    llm = _build_llm(temperature=0.2)  # 代码任务温度更低，减少随机性
    system_msg = SystemMessage(
        content=(
            "你是一位资深 Python 后端工程师。请用清晰、简洁的代码和注释回答编程相关的问题。\n"
            "规范要求：\n"
            "1. 使用严格的类型注解（Type Hints）\n"
            "2. 遵循 PEP8 规范\n"
            "3. 为关键逻辑添加中文注释\n"
            "4. 对用户代码中的 Bug 给出具体的修复建议"
        )
    )

    try:
        response = await llm.ainvoke([system_msg, HumanMessage(content=user_input)])
        answer = response.content
    except Exception as e:
        logger.error(f"❌ Code Agent LLM 调用失败: {e}")
        answer = f"代码任务处理时出错：{str(e)}"

    return {"messages": [AIMessage(content=answer, name="code_agent")]}


async def general_agent_node(state: AgentState) -> Dict:
    """
    通用对话 Agent
    处理不属于 RAG 或代码类的通用问题，可调用 UTILITY_TOOLS。
    """
    user_input = state.get("user_input", "")
    logger.info(f"💬 General Agent 处理: {user_input[:50]}")

    # 绑定实用工具
    llm = _build_llm(temperature=0.7).bind_tools(UTILITY_TOOLS)

    system_msg = SystemMessage(
        content="你是 AI Smart Gateway 的智能助手，请友好、准确地回答用户问题。"
    )

    try:
        response = await llm.ainvoke([system_msg, HumanMessage(content=user_input)])
        answer = response.content or "我明白了，但暂时没有更多信息可以提供。"
    except Exception as e:
        logger.error(f"❌ General Agent LLM 调用失败: {e}")
        answer = f"处理请求时出错：{str(e)}"

    return {"messages": [AIMessage(content=answer, name="general_agent")]}


# ===== 路由函数 =====

def route_to_agent(state: AgentState) -> str:
    """
    根据 supervisor 填写的 next_agent 字段，动态路由到对应的子 Agent 节点。
    LangGraph 条件边（conditional_edge）会调用此函数获取下一节点名称。
    """
    return state.get("next_agent", "general_agent")


# ===== 构建 LangGraph 图 =====

def create_agent_graph() -> StateGraph:
    """
    构建并编译多 Agent 协作图

    图结构：
        supervisor → {rag_agent | code_agent | general_agent} → END
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("code_agent", code_agent_node)
    workflow.add_node("general_agent", general_agent_node)

    # 设置入口
    workflow.set_entry_point("supervisor")

    # supervisor → 条件路由（根据 next_agent 字段分发）
    workflow.add_conditional_edges(
        "supervisor",
        route_to_agent,
        {
            "rag_agent": "rag_agent",
            "code_agent": "code_agent",
            "general_agent": "general_agent",
        },
    )

    # 所有子 Agent 完成后直接结束（可扩展为审查员节点）
    workflow.add_edge("rag_agent", END)
    workflow.add_edge("code_agent", END)
    workflow.add_edge("general_agent", END)

    return workflow.compile()


# ===== 全局图实例（应用启动时创建一次，线程安全） =====
agent_graph = create_agent_graph()


async def run_agent_stream(
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[Dict, None]:
    """
    以流式模式运行 Agent 图，逐步 yield LangGraph 事件字典。

    Args:
        user_message: 用户当前输入
        conversation_history: 历史消息列表（可选），格式:
            [{"role": "user" | "assistant", "content": "..."}]

    Yields:
        LangGraph 内部事件字典，包含节点名称和输出的 state
    """
    # 构建初始消息列表
    messages: list[BaseMessage] = []
    if conversation_history:
        for msg in conversation_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=user_message))

    initial_state: AgentState = {
        "messages": messages,
        "next_agent": "",
        "user_input": user_message,
    }

    # astream_events 会逐步 yield 每个节点执行后的状态快照
    async for event in agent_graph.astream(initial_state):
        yield event


__all__ = ["AgentState", "agent_graph", "run_agent_stream", "create_agent_graph"]
