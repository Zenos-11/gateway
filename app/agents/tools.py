"""
LangChain 工具集
为多 Agent 系统提供可调用的外部工具，遵循 @tool 装饰器规范

工具分类：
- RAG 工具：从知识库检索相关内容
- 代码工具：代码评估与格式化（沙箱化，不允许执行外部命令）
- 通用工具：日期获取等无副作用的辅助工具
"""
from datetime import datetime
from typing import Optional

from langchain_core.tools import tool

from app.core.logger import logger


@tool
async def rag_search(query: str, top_k: int = 5) -> str:
    """
    从知识库向量数据库中检索与 query 最相关的文档片段。
    当需要回答与已上传文档相关的问题时，应优先调用此工具。

    Args:
        query: 检索关键词或问题描述
        top_k: 返回最多多少条结果（默认5）

    Returns:
        格式化后的检索结果字符串，每条结果包含序号和内容
    """
    try:
        from app.infrastructure.vector_store import get_vector_store

        vector_store = await get_vector_store()
        results = await vector_store.search(query=query, n_results=top_k)

        if not results:
            return "知识库中未找到相关文档。请尝试换一种提问方式。"

        parts = []
        for i, r in enumerate(results, 1):
            content = r.get("content", "")
            metadata = r.get("metadata", {})
            filename = metadata.get("filename", "未知文件")
            parts.append(f"[{i}] 来源: {filename}\n{content}")

        return "\n\n".join(parts)

    except Exception as e:
        logger.error(f"❌ rag_search 工具调用失败: {e}")
        return f"检索时发生错误: {str(e)}"


@tool
def get_current_datetime() -> str:
    """
    获取当前的日期和时间（北京时间）。
    当用户询问当前时间、需要生成带时间戳的内容时调用。

    Returns:
        格式化的当前日期时间字符串
    """
    now = datetime.now()
    return now.strftime("%Y年%m月%d日 %H:%M:%S")


@tool
def format_code(code: str, language: str = "python") -> str:
    """
    对代码进行格式化与简单语法检查（仅分析，不执行）。
    当需要美化或检查代码时调用此工具。

    Args:
        code: 需要格式化的源代码
        language: 代码语言（目前支持 python）

    Returns:
        格式化后的代码或错误提示
    """
    if language != "python":
        return f"暂不支持 {language} 的自动格式化，但代码内容如下：\n```{language}\n{code}\n```"

    try:
        import ast

        # 语法检查（仅解析，不执行任何代码）
        ast.parse(code)
        return f"语法检查通过 ✅\n\n```python\n{code}\n```"

    except SyntaxError as e:
        return f"发现语法错误 ❌\n- 行: {e.lineno}\n- 错误: {e.msg}\n\n```python\n{code}\n```"
    except Exception as e:
        return f"代码检查失败: {str(e)}"


# 暴露给 Agent 的工具列表
ALL_TOOLS = [rag_search, get_current_datetime, format_code]

# 按功能分组（供不同 Agent 按需加载）
RAG_TOOLS = [rag_search]
CODE_TOOLS = [format_code]
UTILITY_TOOLS = [get_current_datetime]

__all__ = ["ALL_TOOLS", "RAG_TOOLS", "CODE_TOOLS", "UTILITY_TOOLS"]
