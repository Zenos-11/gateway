# AI Smart Gateway 开发计划

> **项目状态**：Phase 1 基础框架已完成，正在进入 Phase 2 RAG 系统
> **更新时间**：2026-03-12
> **预计完成**：4-6 周

---

## 📊 当前进度

### ✅ Phase 1: 基础框架（已完成）

| 模块 | 状态 | 说明 |
|------|------|------|
| 核心配置 | ✅ | Pydantic Settings，环境变量管理 |
| 日志系统 | ✅ | Loguru 结构化日志，文件轮转 |
| 数据库模型 | ✅ | 8 张核心表，SQLAlchemy 2.0 异步 ORM |
| 数据库连接 | ✅ | 连接池，依赖注入，事务管理 |
| Redis 缓存 | ✅ | 连接池，缓存封装，限流器 |
| JWT 认证 | ✅ | 密码加密，Token 生成/验证 |
| 中间件 | ✅ | 异常处理，请求日志，CORS |
| 认证 API | ✅ | 注册、登录、获取用户信息 |

### 🚧 Phase 2: RAG 系统（进行中）

| 模块 | 状态 | 说明 |
|------|------|------|
| 文档上传 | ⏳ | 接收 PDF/Word/Markdown 文件 |
| 文档解析 | ⏳ | 提取文本内容 |
| 文档分块 | ⏳ | 智能切分（固定大小/语义） |
| 向量化 | ⏳ | Embedding 生成 |
| 向量存储 | ⏳ | ChromaDB 存储 |
| 向量检索 | ⏳ | 相似度搜索 |
| RAG 查询 | ⏳ | 检索 + 生成答案 |

### 📋 Phase 3: 多 Agent 系统（未开始）

| 模块 | 状态 | 说明 |
|------|------|------|
| Agent 编排 | ⏸️ | LangGraph 状态机 |
| 研究员 Agent | ⏸️ | 信息检索与分析 |
| 程序员 Agent | ⏸️ | 代码生成与测试 |
| 审查员 Agent | ⏸️ | 代码审查与优化 |
| 流式响应 | ⏸️ | WebSocket 实时推送 |

---

## 🎯 Phase 2 详细计划：RAG 系统

### Week 1: 文档处理基础

#### Day 1-2: 文档上传与存储

**目标**：实现文档上传 API，支持文件验证和存储

**任务清单**：
- [ ] 创建文档服务层 (`app/services/document_service.py`)
  - 文件上传逻辑
  - 文件类型验证
  - 文件大小限制
  - 生成唯一文件名
- [ ] 创建文档上传 API (`app/api/v1/documents.py`)
  - POST `/api/v1/documents` - 上传文档
  - GET `/api/v1/documents` - 获取文档列表
  - GET `/api/v1/documents/{id}` - 获取文档详情
  - DELETE `/api/v1/documents/{id}` - 删除文档
- [ ] 实现文件存储
  - 创建 uploads/ 目录
  - 按用户分目录存储
  - 支持本地存储
- [ ] 添加异步任务处理
  - 文档上传后异步处理
  - 更新处理状态

**技术要点**：
```python
# 文件上传验证
ALLOWED_FILE_TYPES = ["pdf", "txt", "md", "docx"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 异步处理
from celery import Celery
@celery.task
def process_document(document_id: int):
    # 解析、分块、向量化
    pass
```

**验收标准**：
- ✅ 可以上传 PDF/Word/Markdown 文件
- ✅ 文件类型和大小验证正常
- ✅ 上传后异步处理状态正确更新
- ✅ 可以查询文档列表和详情

---

#### Day 3-4: 文档解析

**目标**：实现多种格式的文档解析

**任务清单**：
- [ ] 创建解析器接口 (`app/utils/parsers/base.py`)
  - 定义统一的解析接口
- [ ] 实现 PDF 解析器 (`app/utils/parsers/pdf_parser.py`)
  - 使用 pypdf 提取文本
  - 处理多列布局
  - 提取元数据（作者、标题）
- [ ] 实现 Word 解析器 (`app/utils/parsers/docx_parser.py`)
  - 使用 python-docx 提取文本
  - 保留格式信息
- [ ] 实现 Markdown 解析器 (`app/utils/parsers/md_parser.py`)
  - 使用 markdownify 提取纯文本
  - 提取代码块
- [ ] 实现 TXT 解析器 (`app/utils/parsers/txt_parser.py`)
  - 处理编码问题（UTF-8、GBK）
  - 去除特殊字符
- [ ] 创建解析器工厂 (`app/utils/parsers/factory.py`)
  - 根据文件类型选择解析器

**技术要点**：
```python
class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file_path: str) -> ParseResult:
        """解析文档，返回文本和元数据"""
        pass

class ParseResult(BaseModel):
    text: str
    metadata: Dict[str, Any]
    page_count: int
    word_count: int
```

**验收标准**：
- ✅ 可以正确解析 PDF 文件
- ✅ 可以正确解析 Word 文件
- ✅ 可以正确解析 Markdown 文件
- ✅ 提取的元数据完整
- ✅ 统计字数准确

---

#### Day 5-7: 文档分块

**目标**：实现智能文档分块策略

**任务清单**：
- [ ] 创建分块器接口 (`app/utils/chunkers/base.py`)
  - 定义统一的分块接口
- [ ] 实现固定大小分块 (`app/utils/chunkers/fixed.py`)
  - 按字符数分块
  - 可配置 chunk_size 和 overlap
- [ ] 实现语义分块 (`app/utils/chunkers/semantic.py`)
  - 按段落分块
  - 按句子边界切分
  - 保持语义完整
- [ ] 实现代码分块 (`app/utils/chunkers/code.py`)
  - 按函数/类分块
  - 保留代码结构
- [ ] 创建分块器工厂 (`app/utils/chunkers/factory.py`)
  - 根据文档类型选择分块策略
- [ ] 实现分块质量评估
  - 计算块的大小分布
  - 检测过小/过大的块

**技术要点**：
```python
class FixedSizeChunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    async def chunk(self, text: str) -> List[Chunk]:
        """滑动窗口分块"""
        pass

class SemanticChunker:
    async def chunk(self, text: str) -> List[Chunk]:
        """按语义边界分块"""
        # 1. 按段落分割
        # 2. 合并短段落
        # 3. 切分长段落
        pass
```

**验收标准**：
- ✅ 固定大小分块正常工作
- ✅ 语义分块保持语义完整
- ✅ 重叠区域正确处理
- ✅ 分块大小分布合理
- ✅ 可以配置不同的分块策略

---

### Week 2: 向量化与存储

#### Day 8-9: Embedding 生成

**目标**：实现文本向量化

**任务清单**：
- [ ] 创建 Embedding 服务 (`app/services/embedding_service.py`)
  - 支持 OpenAI Embeddings
  - 支持本地模型（可选）
  - 批量处理优化
- [ ] 实现向量缓存
  - 缓存已生成的向量
  - 避免重复计算
- [ ] 添加错误处理
  - 重试机制
  - 降级策略
- [ ] 实现批量 Embedding
  - 并发处理
  - 进度跟踪

**技术要点**：
```python
class EmbeddingService:
    async def embed_text(self, text: str) -> List[float]:
        """生成单个文本的向量"""
        pass

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成向量"""
        # 使用 asyncio.gather 并发处理
        pass

    async def embed_chunks(self, chunks: List[Chunk]) -> List[Vector]:
        """为文档块生成向量"""
        # 1. 检查缓存
        # 2. 批量生成
        # 3. 保存缓存
        pass
```

**验收标准**：
- ✅ 可以生成文本向量
- ✅ 批量处理正常工作
- ✅ 缓存机制有效
- ✅ 错误处理完善

---

#### Day 10-11: ChromaDB 集成

**目标**：集成 ChromaDB 向量数据库

**任务清单**：
- [ ] 创建向量存储服务 (`app/infrastructure/vector_store.py`)
  - 初始化 ChromaDB 客户端
  - 创建 Collection
  - 连接池管理
- [ ] 实现向量存储
  - 添加向量
  - 批量添加
  - 更新向量
  - 删除向量
- [ ] 实现向量检索
  - 相似度搜索
  - 过滤条件
  - 结果排序
- [ ] 添加索引优化
  - 配置索引参数
  - 性能测试

**技术要点**：
```python
import chromadb

class VectorStore:
    def __init__(self):
        self.client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT
        )
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )

    async def add_vectors(self, vectors: List[Vector]):
        """批量添加向量"""
        self.collection.add(
            embeddings=[v.embedding for v in vectors],
            documents=[v.text for v in vectors],
            ids=[v.id for v in vectors],
            metadatas=[v.metadata for v in vectors]
        )

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter: Dict = None
    ) -> List[SearchResult]:
        """向量检索"""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter
        )
        return results
```

**验收标准**：
- ✅ ChromaDB 连接正常
- ✅ 可以添加和查询向量
- ✅ 检索结果准确
- ✅ 性能满足要求（< 100ms）

---

#### Day 12-14: RAG 查询实现

**目标**：实现 RAG 问答功能

**任务清单**：
- [ ] 创建 RAG 服务 (`app/services/rag_service.py`)
  - 查询向量化
  - 向量检索
  - 上下文构建
  - LLM 生成
- [ ] 实现检索策略
  - 语义检索
  - 混合检索（BM25 + 语义）
  - 重排序（可选）
- [ ] 实现上下文管理
  - 上下文长度控制
  - 相关性过滤
  - 来源引用
- [ ] 添加流式响应
  - SSE 实时推送
  - 进度反馈
- [ ] 实现多轮对话
  - 对话历史管理
  - 上下文累积

**技术要点**：
```python
class RAGService:
    async def query(
        self,
        query: str,
        conversation_id: Optional[int] = None,
        top_k: int = 5,
        retrieval_method: str = "semantic"
    ) -> RAGResult:
        """RAG 查询"""
        # 1. 查询向量化
        query_embedding = await self.embedding_service.embed_text(query)

        # 2. 检索相关文档
        if retrieval_method == "semantic":
            chunks = await self.vector_store.search(query_embedding, top_k)
        elif retrieval_method == "hybrid":
            chunks = await self.hybrid_search(query, top_k)

        # 3. 构建上下文
        context = self.build_context(chunks)

        # 4. LLM 生成
        answer = await self.llm_service.generate(query, context)

        return RAGResult(
            answer=answer,
            sources=chunks,
            context=context
        )
```

**验收标准**：
- ✅ 可以回答基于文档的问题
- ✅ 检索结果相关
- ✅ 答案准确且有引用
- ✅ 流式响应正常
- ✅ 多轮对话正常

---

### Week 3: API 与优化

#### Day 15-16: RAG API 开发

**目标**：实现 RAG 查询 API

**任务清单**：
- [ ] 创建 RAG API (`app/api/v1/rag.py`)
  - POST `/api/v1/rag/query` - RAG 查询
  - GET `/api/v1/rag/history` - 查询历史
  - POST `/api/v1/rag/feedback` - 用户反馈
- [ ] 实现请求验证
  - 查询长度限制
  - 参数验证
- [ ] 添加响应缓存
  - Redis 缓存查询结果
  - 缓存失效策略
- [ ] 实现流式响应
  - SSE 端点
  - 进度推送

**技术要点**：
```python
@router.post("/rag/query")
async def rag_query(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG 查询"""
    rag_service = RAGService(db)
    result = await rag_service.query(
        query=request.query,
        top_k=request.top_k,
        retrieval_method=request.retrieval_method
    )
    return result

@router.post("/rag/query/stream")
async def rag_query_stream(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """RAG 流式查询"""
    async def generate():
        async for chunk in rag_service.stream_query(request.query):
            yield f"data: {chunk.json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**验收标准**：
- ✅ API 响应正常
- ✅ 参数验证正确
- ✅ 缓存有效
- ✅ 流式响应流畅

---

#### Day 17-18: 性能优化

**目标**：优化 RAG 系统性能

**任务清单**：
- [ ] 优化检索性能
  - 添加向量索引
  - 调整检索参数
  - 批量处理优化
- [ ] 优化 LLM 调用
  - 批量生成
  - 并发控制
  - 超时处理
- [ ] 添加缓存层
  - 查询结果缓存
  - Embedding 缓存
  - 文档缓存
- [ ] 实现异步任务
  - Celery 任务队列
  - 后台处理
  - 进度跟踪

**性能指标**：
- 查询响应时间 < 3 秒
- 首字响应时间 < 500ms
- 并发支持 > 50 QPS

---

#### Day 19-21: 测试与文档

**目标**：完善测试和文档

**任务清单**：
- [ ] 编写单元测试
  - 解析器测试
  - 分块器测试
  - Embedding 测试
  - 检索测试
- [ ] 编写集成测试
  - 完整 RAG 流程测试
  - API 测试
- [ ] 性能测试
  - 压力测试
  - 并发测试
- [ ] 编写文档
  - API 文档
  - 使用指南
  - 部署指南
- [ ] 创建示例
  - 快速开始示例
  - 完整流程演示

---

## 🤖 Phase 3 计划：多 Agent 系统

### Week 4: Agent 编排基础

#### 核心功能
- [ ] LangGraph 状态机设计
- [ ] Agent 通信协议
- [ ] 状态管理
- [ ] 错误处理与重试

### Week 5: Agent 实现

#### 研究员 Agent
- [ ] Web 搜索工具
- [ ] 资料整理工具
- [ ] 需求分析工具

#### 程序员 Agent
- [ ] 代码生成工具
- [ ] 单元测试工具
- [ ] 代码优化工具

#### 审查员 Agent
- [ ] 代码审查工具
- [ ] 安全检查工具
- [ ] 性能分析工具

### Week 6: 流式响应与部署

#### 流式响应
- [ ] WebSocket 实现
- [ ] 实时进度推送
- [ ] Agent 状态广播

#### 部署
- [ ] Docker 镜像优化
- [ ] K8s 部署配置
- [ ] 监控告警
- [ ] 日志收集

---

## 📋 技术债务与优化

### 当前需要处理的技术债务

1. **认证系统完善**
   - [ ] 实现刷新令牌
   - [ ] 实现权限控制
   - [ ] 添加 API Key 认证

2. **向量存储优化**
   - [ ] 添加向量索引
   - [ ] 实现分区存储
   - [ ] 添加备份恢复

3. **监控与告警**
   - [ ] 添加 Prometheus 指标
   - [ ] 实现健康检查
   - [ ] 配置告警规则

4. **文档完善**
   - [ ] API 文档自动生成
   - [ ] 架构文档
   - [ ] 部署文档

---

## 🎯 里程碑

### Milestone 1: RAG 基础版（2 周）
- ✅ 文档上传
- ✅ 文档解析
- ✅ 文档分块
- ✅ 向量化
- ✅ 基础检索

### Milestone 2: RAG 完整版（3 周）
- ✅ RAG 查询
- ✅ 流式响应
- ✅ 多轮对话
- ✅ 性能优化

### Milestone 3: 多 Agent 系统（5 周）
- ✅ Agent 编排
- ✅ 研究员 Agent
- ✅ 程序员 Agent
- ✅ 审查员 Agent

### Milestone 4: 生产就绪（6 周）
- ✅ 完整测试
- ✅ 性能优化
- ✅ 文档完善
- ✅ 部署配置

---

## 💡 下一步行动

### 立即开始（优先级最高）

1. **文档上传功能**（预计 2 天）
   ```bash
   # 创建文件
   app/services/document_service.py
   app/api/v1/documents.py

   # 实现功能
   - 文件上传验证
   - 文件存储
   - 状态更新
   ```

2. **文档解析功能**（预计 2 天）
   ```bash
   # 创建文件
   app/utils/parsers/base.py
   app/utils/parsers/pdf_parser.py
   app/utils/parsers/docx_parser.py

   # 实现功能
   - PDF 解析
   - Word 解析
   - Markdown 解析
   ```

3. **文档分块功能**（预计 1 天）
   ```bash
   # 创建文件
   app/utils/chunkers/base.py
   app/utils/chunkers/fixed.py
   app/utils/chunkers/semantic.py

   # 实现功能
   - 固定大小分块
   - 语义分块
   ```

---

## 📊 进度跟踪

### 本周目标
- [ ] 完成文档上传功能
- [ ] 完成 PDF 解析
- [ ] 完成基础分块
- [ ] 测试完整流程

### 下周目标
- [ ] 完成所有解析器
- [ ] 实现 Embedding
- [ ] 集成 ChromaDB
- [ ] 实现基础检索

### 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| PDF 解析复杂 | 延期 1-2 天 | 使用成熟库，降低预期 |
| ChromaDB 性能 | 检索慢 | 提前测试，准备备选方案 |
| LLM API 限流 | 功能受限 | 实现降级策略，添加队列 |
| 时间紧张 | 无法完成 | 优先实现核心功能，后续迭代 |

---

需要我详细展开某个模块的实现细节吗？或者你想直接开始实现某个功能？
