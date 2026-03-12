"""
文档分块工具
将长文档切分成适合向量化的小块
"""
from typing import List, Dict, Any
import re

from app.core.logger import logger


class DocumentChunker:
    """文档分块器基类"""

    def chunk(self, text: str, **kwargs) -> List[Dict[str, Any]]:
        """
        将文本分块

        Args:
            text: 待分块的文本
            **kwargs: 其他参数

        Returns:
            分块列表，每个元素包含 {content, index, metadata}
        """
        raise NotImplementedError


class FixedSizeChunker(DocumentChunker):
    """固定大小分块器"""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        """
        初始化固定大小分块器

        Args:
            chunk_size: 每块的字符数
            chunk_overlap: 块之间的重叠字符数
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str, **kwargs) -> List[Dict[str, Any]]:
        """按固定大小分块"""
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            if chunk_text.strip():
                chunks.append({
                    "content": chunk_text.strip(),
                    "index": chunk_index,
                    "metadata": {
                        "start": start,
                        "end": end,
                        "chunk_type": "fixed_size",
                    }
                })
                chunk_index += 1

            # 移动到下一块（考虑重叠）
            start = end - self.chunk_overlap

        logger.info(f"✅ 固定大小分块完成: {len(chunks)} 个块")
        return chunks


class RecursiveCharacterChunker(DocumentChunker):
    """递归字符分块器（更智能）"""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: List[str] = None,
    ):
        """
        初始化递归字符分块器

        Args:
            chunk_size: 每块的最大字符数
            chunk_overlap: 块之间的重叠字符数
            separators: 分隔符列表（按优先级排序）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", "！", "？", " ", ""]

    def chunk(self, text: str, **kwargs) -> List[Dict[str, Any]]:
        """递归分块"""
        chunks = self._recursive_split(text, self.separators)
        logger.info(f"✅ 递归分块完成: {len(chunks)} 个块")
        return chunks

    def _recursive_split(self, text: str, separators: List[str]) -> List[Dict[str, Any]]:
        """递归分割文本"""
        if len(text) <= self.chunk_size:
            return [{
                "content": text.strip(),
                "index": 0,
                "metadata": {"chunk_type": "recursive"}
            }]

        # 尝试用第一个分隔符分割
        separator = separators[0]
        splits = text.split(separator)

        chunks = []
        current_chunk = ""
        chunk_index = 0

        for split in splits:
            if len(current_chunk) + len(split) + len(separator) <= self.chunk_size:
                current_chunk += split + separator
            else:
                # 当前块已满，保存
                if current_chunk.strip():
                    chunks.append({
                        "content": current_chunk.strip(),
                        "index": chunk_index,
                        "metadata": {"chunk_type": "recursive"}
                    })
                    chunk_index += 1

                # 如果单个 split 还是太大，递归使用下一个分隔符
                if len(split) > self.chunk_size and len(separators) > 1:
                    sub_chunks = self._recursive_split(split, separators[1:])
                    chunks.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                else:
                    current_chunk = split + separator

        # 保存最后一块
        if current_chunk.strip():
            chunks.append({
                "content": current_chunk.strip(),
                "index": chunk_index,
                "metadata": {"chunk_type": "recursive"}
            })

        return chunks


class SemanticChunker(DocumentChunker):
    """语义分块器（基于段落结构）"""

    def chunk(self, text: str, **kwargs) -> List[Dict[str, Any]]:
        """按语义分块（段落）"""
        # 按双换行符分割段落
        paragraphs = re.split(r'\n\s*\n', text)

        chunks = []
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果段落不超过限制，直接添加
            if len(para) <= 1500:
                chunks.append({
                    "content": para,
                    "index": chunk_index,
                    "metadata": {
                        "chunk_type": "semantic",
                        "is_paragraph": True
                    }
                })
                chunk_index += 1
            else:
                # 段落太长，使用递归分块
                chunker = RecursiveCharacterChunker(chunk_size=1000, chunk_overlap=100)
                sub_chunks = chunker.chunk(para)
                for sub_chunk in sub_chunks:
                    sub_chunk["index"] = chunk_index
                    sub_chunk["metadata"]["chunk_type"] = "semantic_long"
                    chunks.append(sub_chunk)
                    chunk_index += 1

        logger.info(f"✅ 语义分块完成: {len(chunks)} 个块")
        return chunks


def get_chunker(chunker_type: str = "fixed", **kwargs) -> DocumentChunker:
    """
    获取分块器

    Args:
        chunker_type: 分块器类型 (fixed/recursive/semantic)
        **kwargs: 分块器参数

    Returns:
        分块器实例
    """
    chunkers = {
        "fixed": FixedSizeChunker,
        "recursive": RecursiveCharacterChunker,
        "semantic": SemanticChunker,
    }

    if chunker_type not in chunkers:
        raise ValueError(f"不支持的分块器类型: {chunker_type}")

    return chunkers[chunker_type](**kwargs)


async def chunk_document(
    text: str,
    chunker_type: str = "recursive",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    分块文档

    Args:
        text: 待分块的文本
        chunker_type: 分块器类型
        **kwargs: 分块器参数

    Returns:
        分块列表
    """
    chunker = get_chunker(chunker_type, **kwargs)
    return chunker.chunk(text)


__all__ = [
    "DocumentChunker",
    "FixedSizeChunker",
    "RecursiveCharacterChunker",
    "SemanticChunker",
    "get_chunker",
    "chunk_document",
]
