"""
预下载 Chroma 默认 embedding 模型，避免首次文档上传时下载超时。
"""
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.vector_store import build_embedding_function
from app.core.config import settings


async def preload_embedding_model() -> None:
    """执行模型预热下载并做一次最小 embedding 调用。"""
    embedding_function = build_embedding_function()

    print("=" * 60)
    print("开始预下载 Chroma embedding 模型")
    print("=" * 60)
    print(f"模型地址: {settings.CHROMA_EMBEDDING_MODEL_URL}")
    print(f"缓存目录: {Path(settings.CHROMA_EMBEDDING_CACHE_DIR).expanduser()}")
    print(f"下载超时: {settings.CHROMA_EMBEDDING_DOWNLOAD_TIMEOUT_SECONDS} 秒")

    # 第一次调用会触发模型下载
    vectors = embedding_function(["embedding model warmup text"])

    print(f"预热完成，向量维度: {len(vectors[0]) if vectors else 0}")
    print("后续文档上传将复用本地缓存模型。")


if __name__ == "__main__":
    asyncio.run(preload_embedding_model())
