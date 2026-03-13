"""
多 Agent LangGraph 状态机
实现研究员 / 程序员 / 审查员三个专家 Agent 的协作编排。

核心设计思路（回字形路由）：
    用户消息 → 路由节点（supervisor）
        ↓ 判断意图（LLM 分类器）
      rag_agent          → 知识库检索 + 回答
      code_agent         → 代码生成 / 分析
      general_agent      → 通用 LLM 问答
        ↓ 所有分支最终汇聚
       __end__

状态机中唯一共享的状态是 AgentState，多个节点通过对它的读写来传递信息。
"""
from typing import Annotated, Any, AsyncGenerator, Dict, Optional, Sequence, TypedDict

import operator
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from app.agents.tools import RAG_TOOLS, UTILITY_TOOLS
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
    # 用户 ID（用于 RAG 检索时按用户隔离数据）
    user_id: Optional[int]
    # 外部强制路由（来自 API mode），None 表示由 supervisor 自动判断
    forced_agent: Optional[str]


def _normalize_mode_to_agent(mode: str | None) -> Optional[str]:
    """将 API mode 规范化为图内节点名。"""
    if not mode:
        return None

    normalized_mode = mode.strip().lower()
    mapping = {
        "auto": None,
        "rag": "rag_agent",
        "code": "code_agent",
        "general": "general_agent",
    }
    return mapping.get(normalized_mode)


# ===== LLM 工厂 =====

def _build_llm(temperature: float = 0.7, model: str | None = None) -> ChatOpenAI:
    """
    根据配置构建 ChatOpenAI 实例。
    在没有配置 API Key 时降级为 dummy 模式，保证本地可运行。
    """
    return ChatOpenAI(
        model=model or settings.DEFAULT_MODEL,
        temperature=temperature,
        openai_api_key=settings.OPENAI_API_KEY or "sk-placeholder",
        openai_api_base=settings.OPENAI_API_BASE,
        streaming=True,
    )


def _is_model_not_exist_error(error: Exception) -> bool:
    """判断是否是模型不存在错误（DeepSeek / OpenAI 兼容接口通用）。"""
    return "model not exist" in str(error).lower() or "model_not_found" in str(error).lower()


def _get_fallback_model() -> str | None:
    """在 DeepSeek 接口下，返回保底可用模型名。"""
    if "api.deepseek.com" in settings.OPENAI_API_BASE.lower():
        return "deepseek-chat"
    return None


async def _ainvoke_with_fallback(
    llm: ChatOpenAI,
    messages: list,
    temperature: float = 0.7,
) -> Any:
    """
    调用 LLM，若遇到模型不存在错误则自动回退到保底模型重试。
    """
    try:
        return await llm.ainvoke(messages)
    except Exception as error:
        fallback = _get_fallback_model()
        if _is_model_not_exist_error(error) and fallback and llm.model_name != fallback:
            logger.warning(
                f"⚠️ Agent 模型 {llm.model_name} 不可用，自动回退到 {fallback}"
            )
            fallback_llm = _build_llm(temperature=temperature, model=fallback)
            # 如果原 llm 绑定了工具，同样绑定到回退实例上
            if hasattr(llm, "kwargs") and llm.kwargs.get("tools"):
                fallback_llm = fallback_llm.bind_tools(llm.kwargs["tools"])
            return await fallback_llm.ainvoke(messages)
        raise


# ===== 节点函数定义 =====

# Supervisor 使用的意图分类 Prompt
_SUPERVISOR_SYSTEM_PROMPT = """你是一个智能路由助手，负责判断用户问题应该由哪个专家 Agent 来处理。

请分析用户的问题，仅输出以下三个选项之一，不要附加任何其他文字：
- rag_agent：当用户询问需要从文档、知识库、上传资料中检索信息的问题时选择
- code_agent：当用户需要编写代码、调试程序、分析代码逻辑、解释技术实现时选择
- general_agent：所有其他通用问题、日常对话、常识问答时选择

只输出一个选项，不要有前缀、后缀或解释。"""


async def supervisor_node(state: AgentState) -> Dict:
    """
    路由节点（Supervisor）- 使用 LLM 意图分类器
    分析用户意图，决定由哪个子 Agent 来处理。
    意图分类：rag_agent / code_agent / general_agent
    """
    user_input = state.get("user_input", "")
    forced_agent = state.get("forced_agent")

    # 当 API 指定 mode=rag/code/general 时，直接按外部策略路由
    if forced_agent in {"rag_agent", "code_agent", "general_agent"}:
        logger.info("🧭 Supervisor 使用强制路由: {}", forced_agent)
        return {
            "next_agent": forced_agent,
            "messages": [
                AIMessage(content=f"[Supervisor] 使用外部强制路由: {forced_agent}", name="supervisor")
            ],
        }

    # 使用 LLM 分类器而非关键词路由，更准确地理解用户意图
    llm = _build_llm(temperature=0.0)  # temperature=0 保证路由结果稳定可预测
    try:
        response = await _ainvoke_with_fallback(
            llm,
            [
                SystemMessage(content=_SUPERVISOR_SYSTEM_PROMPT),
                HumanMessage(content=user_input),
            ],
            temperature=0.0,
        )
        next_agent = response.content.strip().lower()

        # 防御：若 LLM 输出了非法值，回退到 general_agent
        valid_agents = {"rag_agent", "code_agent", "general_agent"}
        if next_agent not in valid_agents:
            logger.warning(f"⚠️ Supervisor LLM 输出非法值: '{next_agent}'，回退到 general_agent")
            next_agent = "general_agent"

    except Exception as e:
        logger.error(f"❌ Supervisor LLM 分类失败: {e}，回退到 general_agent")
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
    传递 user_id 确保只在当前用户自己的文档范围内检索，防止跨用户数据泄露。
    """
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    logger.info(f"📚 RAG Agent 处理: {user_input[:50]}")

    # 调用 rag_search 工具，携带 user_id 进行权限隔离
    search_result = await RAG_TOOLS[0].ainvoke(
        {"query": user_input, "top_k": 5, "user_id": user_id}
    )

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
        response = await _ainvoke_with_fallback(
            llm, [system_msg, HumanMessage(content=user_input)], temperature=0.3
        )
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
        response = await _ainvoke_with_fallback(
            llm, [system_msg, HumanMessage(content=user_input)], temperature=0.2
        )
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
        response = await _ainvoke_with_fallback(
            llm, [system_msg, HumanMessage(content=user_input)], temperature=0.7
        )
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
    user_id: int | None = None,
    mode: str = "auto",
) -> AsyncGenerator[Dict, None]:
    """
    以流式模式运行 Agent 图，逐步 yield 格式化事件字典。

    使用 astream_events(version="v2") 实现 token 级流式输出：
    - 每个 LLM token 产生时立即推送，而非等待节点完成后再发送
    - 前端可用 SSE 消费此生成器，实现打字机效果

    Args:
        user_message: 用户当前输入
        conversation_history: 历史消息列表（可选），格式:
            [{"role": "user" | "assistant", "content": "..."}]
        user_id: 当前用户 ID（传递给 RAG 检索以隔离数据）
        mode: 路由模式（auto/rag/code/general）

    Yields:
        统一格式的事件字典：
        {"type": "thinking"|"token"|"done"|"error", "agent": str, "content": str}
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
        "user_id": user_id,
        "forced_agent": _normalize_mode_to_agent(mode),
    }

    # astream_events v2：每个 LLM token 都会产生 on_chat_model_stream 事件
    try:
        async for event in agent_graph.astream_events(initial_state, version="v2"):
            event_name = event.get("event", "")
            event_data = event.get("data", {})
            # 从 metadata 中提取当前节点名（LangGraph v2 格式）
            metadata = event.get("metadata", {})
            node_name = metadata.get("langgraph_node", "")

            if event_name == "on_chat_model_stream":
                # LLM 正在逐 token 输出
                chunk = event_data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    event_type = "thinking" if node_name == "supervisor" else "token"
                    yield {
                        "type": event_type,
                        "agent": node_name or "unknown",
                        "content": chunk.content,
                    }

            elif event_name == "on_chain_end" and node_name:
                # 节点执行完毕，推送节点完成信号（可选，帮助前端更新状态）
                output = event_data.get("output", {})
                if isinstance(output, dict) and "next_agent" in output:
                    # supervisor 路由完成，告知前端即将进入哪个 Agent
                    yield {
                        "type": "routing",
                        "agent": "supervisor",
                        "content": output["next_agent"],
                    }

        yield {"type": "done", "agent": "system", "content": ""}

    except Exception as e:
        logger.error(f"❌ Agent 流式运行失败: {e}")
        yield {"type": "error", "agent": "system", "content": str(e)}


async def run_agent(
    user_message: str,
    conversation_history: list[dict] | None = None,
    user_id: int | None = None,
    mode: str = "auto",
) -> str:
    """
    同步（非流式）运行 Agent 图，等待所有节点完成后返回最终答案文本。

    Args:
        user_message: 用户当前输入
        conversation_history: 历史消息列表（可选）
        user_id: 当前用户 ID
        mode: 路由模式（auto/rag/code/general）

    Returns:
        最终 Agent 输出的文本内容
    """
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
        "user_id": user_id,
        "forced_agent": _normalize_mode_to_agent(mode),
    }

    final_state = await agent_graph.ainvoke(initial_state)

    # 从最终消息列表中提取最后一条非 supervisor 的 AI 消息
    for msg in reversed(final_state.get("messages", [])):
        if isinstance(msg, AIMessage) and getattr(msg, "name", "") != "supervisor":
            return msg.content

    return ""

__all__ = ["AgentState", "agent_graph", "run_agent", "run_agent_stream", "create_agent_graph"]
