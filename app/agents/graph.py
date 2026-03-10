from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage
import operator


class AgentState(TypedDict):
    """智能体状态"""
    messages: Annotated[Sequence[BaseMessage], operator.add]


def message_node(state: AgentState) -> AgentState:
    """基础消息处理节点"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if last_message:
        # 简单地返回接收到的消息
        response = f"收到消息: {last_message.content}"
        return {"messages": [HumanMessage(content=response)]}

    return {"messages": [HumanMessage(content="你好！我是 AI 智能助手。")]}


def create_agent_graph() -> StateGraph:
    """创建 LangGraph 智能体图"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("message_processor", message_node)

    # 设置入口点
    workflow.set_entry_point("message_processor")

    # 添加边到结束点
    workflow.add_edge("message_processor", END)

    return workflow.compile()


# 创建全局图实例
agent_graph = create_agent_graph()
