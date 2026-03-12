"""
文档服务
整合文档解析、分块、向量化的完整流程
"""
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Document, DocumentChunk
from app.utils.parsers import parse_document
from app.utils.chunker import chunk_document
from app.infrastructure.vector_store import get_vector_store
from app.core.logger import logger
from app.core.config import settings


class DocumentService:
    """文档服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_document(
        self,
        file_path: str,
        filename: str,
        user_id: int,
        file_type: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """
        上传并处理文档

        Args:
            file_path: 文件路径
            filename: 文件名
            user_id: 用户 ID
            file_type: 文件类型
            title: 文档标题
            metadata: 额外元数据

        Returns:
            创建的文档记录
        """
        start_time = time.time()

        # 1. 创建文档记录
        document = Document(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            file_size=os.path.getsize(file_path),
            processing_status="processing",
            title=title,
            metadata_json=metadata,
        )
        self.db.add(document)
        await self.db.flush()  # 获取 document.id

        logger.info(f"📄 开始处理文档: {filename} (ID: {document.id})")

        try:
            # 2. 解析文档
            logger.info(f"📖 正在解析文档: {filename}")
            text_content = await parse_document(file_path, file_type)

            if not text_content or len(text_content.strip()) < 10:
                raise ValueError("文档内容为空或太短")

            # 3. 分块
            logger.info(f"✂️ 正在分块文档")
            chunks_data = await chunk_document(
                text_content,
                chunker_type="recursive",
                chunk_size=1000,
                chunk_overlap=200,
            )

            # 4. 创建文档块记录
            logger.info(f"💾 正在保存 {len(chunks_data)} 个文档块到数据库")
            chunk_records = []
            vector_store_data = {
                "texts": [],
                "metadatas": [],
                "ids": [],
            }

            for chunk_data in chunks_data:
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_data["index"],
                    content=chunk_data["content"],
                    embedding_status="pending",
                    metadata_json=chunk_data.get("metadata", {}),
                )
                chunk_records.append(chunk)
                self.db.add(chunk)

            await self.db.flush()

            # 5. 准备向量化数据
            for chunk_record in chunk_records:
                vector_store_data["texts"].append(chunk_record.content)
                vector_store_data["metadatas"].append({
                    "document_id": document.id,
                    "chunk_id": chunk_record.id,
                    "filename": filename,
                    "user_id": user_id,
                })
                vector_store_data["ids"].append(f"chunk_{chunk_record.id}")

            # 6. 向量化并存储
            logger.info(f"🔍 正在向量化并存储 {len(chunk_records)} 个文档块")
            vector_store = await get_vector_store()
            await vector_store.add_documents(
                texts=vector_store_data["texts"],
                metadatas=vector_store_data["metadatas"],
                ids=vector_store_data["ids"],
            )

            # 7. 更新状态
            document.chunk_count = len(chunk_records)
            document.vector_count = len(chunk_records)
            document.processing_status = "completed"
            document.indexing_time_ms = int((time.time() - start_time) * 1000)

            # 更新所有块的 embedding 状态
            for chunk in chunk_records:
                chunk.embedding_status = "completed"

            await self.db.commit()

            processing_time = time.time() - start_time
            logger.info(f"✅ 文档处理完成: {filename}")
            logger.info(f"   - 文档块数: {len(chunk_records)}")
            logger.info(f"   - 处理时间: {processing_time:.2f}秒")

            return document

        except Exception as e:
            # 更新状态为失败
            document.processing_status = "failed"
            await self.db.commit()

            logger.error(f"❌ 文档处理失败: {filename}, 错误: {e}")
            raise

    async def get_document(
        self,
        document_id: int,
        user_id: int,
    ) -> Optional[Document]:
        """
        获取文档详情

        Args:
            document_id: 文档 ID
            user_id: 用户 ID

        Returns:
            文档对象
        """
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        user_id: int,
        status: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Document]:
        """
        获取用户的文档列表

        Args:
            user_id: 用户 ID
            status: 状态过滤
            file_type: 文件类型过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            文档列表
        """
        query = select(Document).where(Document.user_id == user_id)

        if status:
            query = query.where(Document.processing_status == status)

        if file_type:
            query = query.where(Document.file_type == file_type)

        query = query.order_by(Document.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_document(
        self,
        document_id: int,
        user_id: int,
    ) -> bool:
        """
        删除文档

        Args:
            document_id: 文档 ID
            user_id: 用户 ID

        Returns:
            是否删除成功
        """
        try:
            # 1. 获取文档
            document = await self.get_document(document_id, user_id)
            if not document:
                return False

            # 2. 从向量存储中删除
            vector_store = await get_vector_store()
            await vector_store.delete_by_metadata({
                "document_id": document_id
            })

            # 3. 删除数据库记录（级联删除 chunks）
            await self.db.delete(document)
            await self.db.commit()

            logger.info(f"✅ 文档已删除: {document.filename} (ID: {document_id})")
            return True

        except Exception as e:
            logger.error(f"❌ 删除文档失败: {e}")
            await self.db.rollback()
            return False

    async def get_document_chunks(
        self,
        document_id: int,
        user_id: int,
    ) -> List[DocumentChunk]:
        """
        获取文档的所有块

        Args:
            document_id: 文档 ID
            user_id: 用户 ID

        Returns:
            文档块列表
        """
        # 验证文档权限
        document = await self.get_document(document_id, user_id)
        if not document:
            return []

        result = await self.db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())


__all__ = ["DocumentService"]
