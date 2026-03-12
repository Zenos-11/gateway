"""
RAG 查询服务
整合向量检索和 LLM 生成
"""
from typing import List, Dict, Any, Optional
import time

from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.infrastructure.vector_store import get_vector_store
from app.models.database import User, Conversation, Message
from app.core.config import settings
from app.core.logger import logger


class RAGService:
    """RAG 查询服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_client = None

    def _get_llm_client(self) -> AsyncOpenAI:
        """获取 LLM 客户端"""
        if self.llm_client is None:
            self.llm_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_API_BASE,
            )
        return self.llm_client

    async def query(
        self,
        query_text: str,
        user_id: int,
        conversation_id: Optional[int] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        RAG 查询

        Args:
            query_text: 查询文本
            user_id: 用户 ID
            conversation_id: 会话 ID（可选，用于多轮对话）
            top_k: 检索的文档块数量
            score_threshold: 相似度阈值
            model: 模型名称
            temperature: 温度参数

        Returns:
            查询结果，包含答案、来源等
        """
        start_time = time.time()

        # 1. 向量检索
        logger.info(f"🔍 开始检索相关文档: {query_text[:50]}...")
        retrieval_start = time.time()

        vector_store = await get_vector_store()

        # 按用户过滤检索结果
        search_results = await vector_store.search(
            query=query_text,
            n_results=top_k,
            where={"user_id": str(user_id)} if user_id else None,
        )

        retrieval_time = (time.time() - retrieval_start) * 1000

        # 过滤低分结果
        if score_threshold:
            search_results = [
                r for r in search_results
                if r.get("distance", 1) <= score_threshold
            ]

        if not search_results:
            logger.warning("⚠️ 未找到相关文档")
            return {
                "answer": "抱歉，我没有找到相关的文档来回答您的问题。",
                "sources": [],
                "confidence": 0.0,
                "retrieval_time_ms": int(retrieval_time),
                "generation_time_ms": 0,
            }

        logger.info(f"✅ 检索完成，找到 {len(search_results)} 个相关文档块")

        # 2. 构建上下文
        context_parts = []
        sources = []

        for i, result in enumerate(search_results):
            content = result.get("content", "")
            metadata = result.get("metadata", {})

            context_parts.append(f"[文档{i+1}] {content}")

            sources.append({
                "content": content[:200] + "..." if len(content) > 200 else content,
                "metadata": metadata,
                "score": result.get("distance", 0),
            })

        context = "\n\n".join(context_parts)

        # 3. 构建提示词
        system_prompt = """你是一个专业的AI助手，擅长根据提供的文档内容回答用户问题。

请遵循以下原则：
1. 只使用提供的文档内容来回答问题
2. 如果文档中没有相关信息，明确告知用户
3. 回答时要准确、客观，引用文档中的具体内容
4. 使用清晰的格式组织答案

文档内容：
{context}"""

        user_prompt = f"问题：{query_text}\n\n请根据上述文档内容回答这个问题。"

        # 4. 调用 LLM
        logger.info(f"🤖 开始生成答案...")
        generation_start = time.time()

        try:
            llm_client = self._get_llm_client()

            response = await llm_client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt.format(context=context)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature or settings.DEFAULT_TEMPERATURE,
                max_tokens=settings.DEFAULT_MAX_TOKENS,
            )

            answer = response.choices[0].message.content
            tokens_used = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        except Exception as e:
            logger.error(f"❌ LLM 调用失败: {e}")
            answer = "抱歉，生成答案时出现错误，请稍后重试。"
            tokens_used = {}

        generation_time = (time.time() - generation_start) * 1000
        total_time = (time.time() - start_time) * 1000

        logger.info(f"✅ RAG 查询完成")
        logger.info(f"   - 检索时间: {retrieval_time:.0f}ms")
        logger.info(f"   - 生成时间: {generation_time:.0f}ms")
        logger.info(f"   - 总时间: {total_time:.0f}ms")

        # 5. 保存对话记录（如果提供了 conversation_id）
        if conversation_id:
            await self._save_conversation(
                conversation_id=conversation_id,
                query=query_text,
                answer=answer,
                tokens_used=tokens_used,
                latency_ms=int(total_time),
            )

        return {
            "answer": answer,
            "sources": sources,
            "confidence": self._calculate_confidence(search_results),
            "retrieval_time_ms": int(retrieval_time),
            "generation_time_ms": int(generation_time),
            "total_time_ms": int(total_time),
            "tokens_used": tokens_used,
        }

    def _calculate_confidence(self, search_results: List[Dict[str, Any]]) -> float:
        """
        计算置信度

        Args:
            search_results: 检索结果

        Returns:
            置信度分数 (0-1)
        """
        if not search_results:
            return 0.0

        # 使用平均距离的倒数作为置信度
        distances = [r.get("distance", 1) for r in search_results]
        avg_distance = sum(distances) / len(distances)

        # 距离越小，置信度越高
        confidence = max(0.0, 1.0 - avg_distance)
        return round(confidence, 2)

    async def _save_conversation(
        self,
        conversation_id: int,
        query: str,
        answer: str,
        tokens_used: Dict[str, int],
        latency_ms: int,
    ) -> None:
        """
        保存对话记录

        Args:
            conversation_id: 会话 ID
            query: 用户查询
            answer: AI 回答
            tokens_used: Token 使用情况
            latency_ms: 延迟
        """
        try:
            # 保存用户消息
            user_message = Message(
                conversation_id=conversation_id,
                role="user",
                content=query,
                content_type="text",
            )
            self.db.add(user_message)

            # 保存助手消息
            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                content_type="text",
                model_name=settings.DEFAULT_MODEL,
                total_tokens=tokens_used.get("total_tokens"),
                prompt_tokens=tokens_used.get("prompt_tokens"),
                completion_tokens=tokens_used.get("completion_tokens"),
                latency_ms=latency_ms,
            )
            self.db.add(assistant_message)

            # 更新会话统计
            await self.db.execute(
                f"""
                UPDATE conversations
                SET message_count = message_count + 2,
                    total_tokens = total_tokens + {tokens_used.get('total_tokens', 0)},
                    updated_at = NOW()
                WHERE id = {conversation_id}
                """
            )

            await self.db.commit()
            logger.debug("💾 对话记录已保存")

        except Exception as e:
            logger.error(f"❌ 保存对话记录失败: {e}")
            await self.db.rollback()


__all__ = ["RAGService"]
