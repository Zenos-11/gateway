"""
文档管理 API 路由
提供文档上传、查询、删除等功能
"""
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.api.deps import require_current_user, User
from app.services.document_service import DocumentService
from app.models.database import Document
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()


@router.post("/documents", summary="上传文档")
async def upload_document(
    file: UploadFile = File(..., description="文档文件"),
    title: Optional[str] = Form(None, description="文档标题"),
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    上传文档到知识库

    支持的文件格式：
    - PDF (.pdf)
    - 纯文本 (.txt)
    - Markdown (.md)
    - Word 文档 (.docx)

    最大文件大小：10MB
    """
    # 1. 验证文件
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )

    # 获取文件扩展名
    file_ext = Path(file.filename).suffix.lstrip('.').lower()
    if file_ext not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_ext}。支持的类型: {', '.join(settings.ALLOWED_FILE_TYPES)}"
        )

    # 2. 检查文件大小
    file_content = await file.read()
    file_size = len(file_content)

    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件过大。最大允许: {settings.MAX_FILE_SIZE // 1024 // 1024}MB"
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容为空"
        )

    # 3. 保存文件
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(file_content)

    logger.info(f"📄 文件已保存: {file_path}")

    # 4. 处理文档
    try:
        document_service = DocumentService(db)
        document = await document_service.upload_document(
            file_path=str(file_path),
            filename=file.filename,
            user_id=current_user.id,
            file_type=file_ext,
            title=title,
        )

        return {
            "success": True,
            "data": {
                "id": document.id,
                "filename": document.filename,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "chunk_count": document.chunk_count,
                "status": document.processing_status,
                "created_at": document.created_at.isoformat(),
            }
        }

    except Exception as e:
        # 删除已上传的文件
        if file_path.exists():
            file_path.unlink()

        logger.error(f"❌ 文档处理失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档处理失败: {str(e)}"
        )


@router.get("/documents", summary="获取文档列表")
async def list_documents(
    status_filter: Optional[str] = None,
    file_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的文档列表

    支持按状态和文件类型过滤
    """
    try:
        document_service = DocumentService(db)
        documents = await document_service.list_documents(
            user_id=current_user.id,
            status=status_filter,
            file_type=file_type,
            limit=page_size,
            offset=(page - 1) * page_size,
        )

        return {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": doc.id,
                        "filename": doc.filename,
                        "title": doc.title,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                        "chunk_count": doc.chunk_count,
                        "status": doc.processing_status,
                        "created_at": doc.created_at.isoformat(),
                    }
                    for doc in documents
                ],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                }
            }
        }

    except Exception as e:
        logger.error(f"❌ 获取文档列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档列表失败: {str(e)}"
        )


@router.get("/documents/{document_id}", summary="获取文档详情")
async def get_document(
    document_id: int,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个文档的详细信息"""
    try:
        document_service = DocumentService(db)
        document = await document_service.get_document(document_id, current_user.id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )

        return {
            "success": True,
            "data": {
                "id": document.id,
                "filename": document.filename,
                "title": document.title,
                "author": document.author,
                "subject": document.subject,
                "keywords": document.keywords,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "chunk_count": document.chunk_count,
                "vector_count": document.vector_count,
                "status": document.processing_status,
                "indexing_time_ms": document.indexing_time_ms,
                "created_at": document.created_at.isoformat(),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取文档详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档详情失败: {str(e)}"
        )


@router.delete("/documents/{document_id}", summary="删除文档")
async def delete_document(
    document_id: int,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除文档及其相关数据"""
    try:
        document_service = DocumentService(db)
        success = await document_service.delete_document(document_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )

        return {
            "success": True,
            "message": "文档已删除"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除文档失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除文档失败: {str(e)}"
        )


@router.get("/documents/{document_id}/chunks", summary="获取文档块")
async def get_document_chunks(
    document_id: int,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取文档的所有分块"""
    try:
        document_service = DocumentService(db)
        chunks = await document_service.get_document_chunks(document_id, current_user.id)

        return {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
                        "page_number": chunk.page_number,
                        "token_count": chunk.token_count,
                        "embedding_status": chunk.embedding_status,
                    }
                    for chunk in chunks
                ]
            }
        }

    except Exception as e:
        logger.error(f"❌ 获取文档块失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档块失败: {str(e)}"
        )
