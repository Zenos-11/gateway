"""
向量存储服务
使用 ChromaDB 进行向量存储和检索
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import os
import hashlib

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random

from app.core.config import settings
from app.core.logger import logger


class StableONNXMiniLMEmbeddingFunction(embedding_functions.ONNXMiniLM_L6_V2):
    """带可配置超时与缓存目录的 ONNX embedding 函数。"""

    def __init__(
        self,
        model_url: str,
        cache_dir: str,
        download_timeout_seconds: int,
    ) -> None:
        self.MODEL_DOWNLOAD_URL = model_url
        self.DOWNLOAD_PATH = Path(cache_dir).expanduser()
        self._download_timeout_seconds = max(download_timeout_seconds, 60)
        super().__init__()

    @retry(  # type: ignore[misc]
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_random(min=1, max=3),
        retry=retry_if_exception(lambda e: "does not match expected SHA256" in str(e)),
    )
    def _download(self, url: str, fname: str, chunk_size: int = 1024) -> None:
        """覆写下载逻辑：增加请求超时，降低慢网环境超时概率。"""
        timeout = httpx.Timeout(
            connect=30.0,
            read=float(self._download_timeout_seconds),
            write=float(self._download_timeout_seconds),
            pool=30.0,
        )

        with httpx.stream("GET", url, timeout=timeout) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))

            with open(fname, "wb") as file, self.tqdm(
                desc=str(fname),
                total=total,
                unit="iB",
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for data in resp.iter_bytes(chunk_size=chunk_size):
                    size = file.write(data)
                    bar.update(size)

        if not self._verify_sha256(fname, self._MODEL_SHA256):
            os.remove(fname)
            raise ValueError(
                f"Downloaded file {fname} does not match expected SHA256 hash. "
                "Corrupted download or malicious file."
            )

    @staticmethod
    def _verify_sha256(file_path: str, expected_sha256: str) -> bool:
        """校验下载文件的 SHA256，防止损坏文件进入缓存。"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest() == expected_sha256


def build_embedding_function() -> StableONNXMiniLMEmbeddingFunction:
    """构建可配置的默认 embedding 函数。"""
    return StableONNXMiniLMEmbeddingFunction(
        model_url=settings.CHROMA_EMBEDDING_MODEL_URL,
        cache_dir=settings.CHROMA_EMBEDDING_CACHE_DIR,
        download_timeout_seconds=settings.CHROMA_EMBEDDING_DOWNLOAD_TIMEOUT_SECONDS,
    )


class VectorStore:
    """向量存储服务"""

    def __init__(
        self,
        collection_name: str = "documents",
        host: str = None,
        port: int = None,
    ):
        """
        初始化向量存储

        Args:
            collection_name: 集合名称
            host: ChromaDB 主机
            port: ChromaDB 端口
        """
        self.collection_name = collection_name
        self.host = host or settings.CHROMA_HOST
        self.port = port or settings.CHROMA_PORT
        self.client = None
        self.collection = None
        self.embedding_function = build_embedding_function()

    async def connect(self) -> None:
        """连接到 ChromaDB"""
        try:
            # 使用 HTTP 模式连接 ChromaDB
            self.client = chromadb.HttpClient(
                host=self.host,
                port=self.port,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )

            # 获取或创建集合
            try:
                self.collection = self.client.get_collection(
                    name=self.collection_name,
                    embedding_function=self.embedding_function,
                )
                logger.info(f"✅ 连接到现有集合: {self.collection_name}")
            except Exception:
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Document chunks for RAG"},
                    embedding_function=self.embedding_function,
                )
                logger.info(f"✅ 创建新集合: {self.collection_name}")

        except Exception as e:
            logger.error(f"❌ ChromaDB 连接失败: {e}")
            raise

    async def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        """
        添加文档到向量存储

        Args:
            texts: 文本列表
            metadatas: 元数据列表
            ids: 文档 ID 列表
        """
        try:
            if not self.collection:
                await self.connect()

            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info(f"✅ 成功添加 {len(texts)} 个文档到向量存储")

        except Exception as e:
            logger.error(f"❌ 添加文档失败: {e}")
            raise

    async def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        向量搜索

        Args:
            query: 查询文本
            n_results: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件

        Returns:
            搜索结果列表
        """
        try:
            if not self.collection:
                await self.connect()

            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                where_document=where_document,
            )

            # 格式化结果
            formatted_results = []
            if results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    formatted_results.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "id": results['ids'][0][i] if results['ids'] else None,
                        "distance": results['distances'][0][i] if 'distances' in results and results['distances'] else None,
                    })

            logger.info(f"✅ 搜索完成，返回 {len(formatted_results)} 个结果")
            return formatted_results

        except Exception as e:
            logger.error(f"❌ 搜索失败: {e}")
            return []

    async def delete(
        self,
        ids: List[str],
    ) -> None:
        """
        删除文档

        Args:
            ids: 文档 ID 列表
        """
        try:
            if not self.collection:
                await self.connect()

            self.collection.delete(ids=ids)
            logger.info(f"✅ 成功删除 {len(ids)} 个文档")

        except Exception as e:
            logger.error(f"❌ 删除文档失败: {e}")
            raise

    async def delete_by_metadata(
        self,
        where: Dict[str, Any],
    ) -> None:
        """
        按元数据删除文档

        Args:
            where: 元数据过滤条件
        """
        try:
            if not self.collection:
                await self.connect()

            # 先查询获取 ID
            results = self.collection.get(where=where)
            if results and results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"✅ 成功删除 {len(results['ids'])} 个文档")

        except Exception as e:
            logger.error(f"❌ 按元数据删除失败: {e}")
            raise

    async def get_collection_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息

        Returns:
            统计信息字典
        """
        try:
            if not self.collection:
                await self.connect()

            count = self.collection.count()
            return {
                "collection_name": self.collection_name,
                "count": count,
            }

        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}

    async def reset_collection(self) -> None:
        """重置集合（删除所有数据）"""
        try:
            if not self.client:
                await self.connect()

            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Document chunks for RAG"}
            )
            logger.info(f"✅ 集合已重置: {self.collection_name}")

        except Exception as e:
            logger.error(f"❌ 重置集合失败: {e}")
            raise


# 全局向量存储实例
_vector_store: Optional[VectorStore] = None


async def get_vector_store() -> VectorStore:
    """
    获取向量存储单例

    Returns:
        VectorStore 实例
    """
    global _vector_store

    if _vector_store is None:
        _vector_store = VectorStore()
        await _vector_store.connect()

    return _vector_store


async def init_vector_store() -> None:
    """初始化向量存储"""
    try:
        vector_store = await get_vector_store()
        stats = await vector_store.get_collection_stats()
        logger.info(f"✅ 向量存储初始化成功，文档数: {stats.get('count', 0)}")
    except Exception as e:
        logger.warning(f"⚠️ 向量存储初始化失败: {e}")
        # 不抛出异常，允许应用在没有向量存储的情况下运行


async def close_vector_store() -> None:
    """关闭向量存储连接"""
    # ChromaDB HTTP 客户端不需要显式关闭
    logger.info("✅ 向量存储连接已关闭")


__all__ = [
    "StableONNXMiniLMEmbeddingFunction",
    "build_embedding_function",
    "VectorStore",
    "get_vector_store",
    "init_vector_store",
    "close_vector_store",
]
