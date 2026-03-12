"""
RAG 查询服务
整合向量检索和 LLM 生成
"""
from typing import AsyncGenerator, List, Dict, Any, Optional
import json
import time

from sqlalchemy import update
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

    @staticmethod
    def _is_model_not_exist_error(error: Exception) -> bool:
        """判断是否是模型不存在错误。"""
        error_text = str(error).lower()
        return "model not exist" in error_text or "model_not_found" in error_text

    @staticmethod
    def _is_deepseek_base_url() -> bool:
        """判断当前是否使用 DeepSeek OpenAI 兼容接口。"""
        return "api.deepseek.com" in settings.OPENAI_API_BASE.lower()

    @classmethod
    def _get_fallback_model(cls, failed_model: str) -> Optional[str]:
        """根据失败模型返回可回退模型。"""
        if cls._is_deepseek_base_url() and failed_model != "deepseek-chat":
            return "deepseek-chat"
        return None

    async def _create_completion_with_fallback(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: Optional[float],
    ) -> tuple[Any, str]:
        """创建非流式补全，模型不存在时自动回退。"""
        llm_client = self._get_llm_client()
        selected_model = model or settings.DEFAULT_MODEL

        try:
            response = await llm_client.chat.completions.create(
                model=selected_model,
                messages=messages,
                temperature=temperature or settings.DEFAULT_TEMPERATURE,
                max_tokens=settings.DEFAULT_MAX_TOKENS,
            )
            return response, selected_model
        except Exception as error:
            fallback_model = self._get_fallback_model(selected_model)
            if self._is_model_not_exist_error(error) and fallback_model:
                logger.warning(
                    "⚠️ 模型 {} 不可用，自动回退到 {}",
                    selected_model,
                    fallback_model,
                )
                response = await llm_client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    temperature=temperature or settings.DEFAULT_TEMPERATURE,
                    max_tokens=settings.DEFAULT_MAX_TOKENS,
                )
                return response, fallback_model
            raise

    async def _create_stream_with_fallback(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: Optional[float],
    ) -> tuple[Any, str]:
        """创建流式补全，模型不存在时自动回退。"""
        llm_client = self._get_llm_client()
        selected_model = model or settings.DEFAULT_MODEL

        try:
            stream = await llm_client.chat.completions.create(
                model=selected_model,
                messages=messages,
                temperature=temperature or settings.DEFAULT_TEMPERATURE,
                max_tokens=settings.DEFAULT_MAX_TOKENS,
                stream=True,
            )
            return stream, selected_model
        except Exception as error:
            fallback_model = self._get_fallback_model(selected_model)
            if self._is_model_not_exist_error(error) and fallback_model:
                logger.warning(
                    "⚠️ 流式模型 {} 不可用，自动回退到 {}",
                    selected_model,
                    fallback_model,
                )
                stream = await llm_client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    temperature=temperature or settings.DEFAULT_TEMPERATURE,
                    max_tokens=settings.DEFAULT_MAX_TOKENS,
                    stream=True,
                )
                return stream, fallback_model
            raise

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
            # 文档入库时 user_id 以 int 写入 metadata，这里保持同类型避免过滤失效。
            where={"user_id": user_id} if user_id else None,
        )
        raw_results_count = len(search_results)

        retrieval_time = (time.time() - retrieval_start) * 1000

        # 过滤低分结果
        if score_threshold is not None:
            search_results = [
                r for r in search_results
                if r.get("distance", 1) <= score_threshold
            ]
            logger.info(
                "🔎 阈值过滤完成: threshold={}, before={}, after={}",
                score_threshold,
                raw_results_count,
                len(search_results),
            )

        if not search_results:
            logger.warning("⚠️ 未找到相关文档")
            total_time = (time.time() - start_time) * 1000
            answer = "抱歉，我没有找到相关的文档来回答您的问题。"
            if score_threshold is not None and raw_results_count > 0:
                answer = (
                    f"已检索到 {raw_results_count} 条候选文档，但被 score_threshold={score_threshold} 全部过滤。"
                    "建议调大该值或不传该参数后重试。"
                )
            return {
                "answer": answer,
                "sources": [],
                "confidence": 0.0,
                "retrieval_time_ms": int(retrieval_time),
                "generation_time_ms": 0,
                "total_time_ms": int(total_time),
                "tokens_used": {},
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
        used_model = model or settings.DEFAULT_MODEL

        try:
            response, used_model = await self._create_completion_with_fallback(
                messages=[
                    {"role": "system", "content": system_prompt.format(context=context)},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=temperature,
            )

            answer = response.choices[0].message.content or ""
            usage = response.usage
            tokens_used = {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            }

        except Exception as e:
            logger.error(f"❌ LLM 调用失败（model={used_model}）: {e}")
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
                model_name=used_model,
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
        model_name: str,
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
                model_name=model_name,
                total_tokens=tokens_used.get("total_tokens"),
                prompt_tokens=tokens_used.get("prompt_tokens"),
                completion_tokens=tokens_used.get("completion_tokens"),
                latency_ms=latency_ms,
            )
            self.db.add(assistant_message)

            # 使用 ORM update 避免 SQL 注入，参数由 SQLAlchemy 绑定
            await self.db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    message_count=Conversation.message_count + 2,
                    total_tokens=Conversation.total_tokens + tokens_used.get("total_tokens", 0),
                )
            )

            await self.db.commit()
            logger.debug("💾 对话记录已保存")

        except Exception as e:
            logger.error(f"❌ 保存对话记录失败: {e}")
            await self.db.rollback()

    async def stream_query(
        self,
        query_text: str,
        user_id: int,
        conversation_id: Optional[int] = None,
        top_k: int = 5,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """
        RAG 流式查询（SSE），先检索文档，再用 LLM 流式生成答案

        Yields:
            SSE 格式的 JSON 字符串事件
        """
        # 1. 向量检索
        vector_store = await get_vector_store()
        search_results = await vector_store.search(
            query=query_text,
            n_results=top_k,
            # 与 query() 保持一致，避免 metadata 类型不一致导致漏检。
            where={"user_id": user_id} if user_id else None,
        )

        if not search_results:
            yield f"data: {json.dumps({'type': 'error', 'content': '未找到相关文档'}, ensure_ascii=False)}\n\n"
            return

        # 构建检索结果事件（提前返回来源信息）
        sources = [
            {
                "content": r.get("content", "")[:200],
                "metadata": r.get("metadata", {}),
                "score": r.get("distance", 0),
            }
            for r in search_results
        ]
        yield f"data: {json.dumps({'type': 'sources', 'content': sources}, ensure_ascii=False)}\n\n"

        # 2. 构建上下文与提示词
        context = "\n\n".join(
            f"[文档{i+1}] {r.get('content', '')}"
            for i, r in enumerate(search_results)
        )
        system_prompt = (
            "你是一个专业的AI助手，擅长根据提供的文档内容回答用户问题。\n\n"
            "请遵循以下原则：\n"
            "1. 只使用提供的文档内容来回答问题\n"
            "2. 如果文档中没有相关信息，明确告知用户\n"
            "3. 回答时要准确、客观，引用文档中的具体内容\n\n"
            f"文档内容：\n{context}"
        )

        # 3. LLM 流式生成
        full_answer = []
        used_model = model or settings.DEFAULT_MODEL
        try:
            stream, used_model = await self._create_stream_with_fallback(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"问题：{query_text}"},
                ],
                model=model,
                temperature=temperature,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_answer.append(delta.content)
                    yield f"data: {json.dumps({'type': 'token', 'content': delta.content}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"❌ 流式 LLM 调用失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 4. 保存对话记录
        if conversation_id and full_answer:
            answer_text = "".join(full_answer)
            await self._save_conversation(
                conversation_id=conversation_id,
                query=query_text,
                answer=answer_text,
                model_name=used_model,
                tokens_used={},
                latency_ms=0,
            )

        yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"


__all__ = ["RAGService"]
