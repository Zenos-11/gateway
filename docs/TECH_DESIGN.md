# AI Smart Gateway 技术设计方案

> **项目定位**：基于 FastAPI + LangGraph 的企业级 AI 应用网关
> **目标场景**：智能知识库问答 + 多 Agent 协作任务处理
> **核心价值**：展示 RAG 工程化能力 + 多 Agent 编排能力 + 高并发架构设计

---

## 📐 一、系统架构设计

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         Client Layer                        │
│  (Web App / WebSocket Client / REST API Client)             │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    API Gateway Layer                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI + CORS + Rate Limiting + Auth Middleware   │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
┌──────▼──────┐  ┌────▼─────┐  ┌─────▼──────┐
│   Router    │  │ Router   │  │  Router    │
│  Layer      │  │ Layer    │  │  Layer     │
└──────┬──────┘  └────┬─────┘  └─────┬──────┘
       │              │               │
┌──────▼──────────────▼───────────────▼──────┐
│              Service Layer                 │
│  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
│  │ RAG      │  │ Multi-   │  │ Chat    │  │
│  │ Service  │  │ Agent    │  │ Service │  │
│  └──────────┘  └──────────┘  └─────────┘  │
└──────┬──────────────┬───────────────┬──────┘
       │              │               │
┌──────▼──────────────▼───────────────▼──────┐
│             Agent Layer (LangGraph)         │
│  ┌──────────────┐  ┌──────────────────┐    │
│  │ RAG Agent    │  │ Multi-Agent      │    │
│  │              │  │ Orchestrator     │    │
│  │ - Retriever  │  │                  │    │
│  │ - Generator  │  │ - Researcher     │    │
│  │              │  │ - Coder          │    │
│  └──────────────┘  │ - Reviewer       │    │
│                    └──────────────────┘    │
└────────────────────────────────────────────┘
       │              │               │
┌──────▼──────────────▼───────────────▼──────┐
│           Infrastructure Layer              │
│  ┌─────────┐  ┌─────────┐  ┌───────────┐  │
│  │ Vector  │  │  Redis  │  │ PostgreSQL│  │
│  │ DB      │  │  Cache  │  │           │  │
│  └─────────┘  └─────────┘  └───────────┘  │
└────────────────────────────────────────────┘
```

### 1.2 核心模块职责

| 层级 | 模块 | 职责 | 技术选型 |
|------|------|------|----------|
| **Router 层** | routes/* | 处理 HTTP 请求、参数验证、权限控制 | FastAPI, Pydantic |
| **Service 层** | services/* | 业务逻辑编排、事务管理、缓存策略 | 自定义 Service 类 |
| **Agent 层** | agents/* | AI 决策、工具调用、状态流转 | LangGraph, LangChain |
| **Infra 层** | infrastructure/* | 数据持久化、向量检索、消息队列 | PostgreSQL, ChromaDB, Redis |

---

## 📊 二、数据库设计

### 2.1 PostgreSQL 表结构

```sql
-- 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 文档表（RAG 知识库）
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL,  -- pdf/txt/md/docx
    file_size INTEGER,
    chunk_count INTEGER,
    vector_count INTEGER,
    status VARCHAR(20) DEFAULT 'processing',  -- processing/ready/failed
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话会话表
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255),
    agent_type VARCHAR(50),  -- rag/multi_agent/chat
    model_name VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息表
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    role VARCHAR(20) NOT NULL,  -- user/assistant/system
    content TEXT NOT NULL,
    tokens_used INTEGER,
    latency_ms INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent 执行记录表
CREATE TABLE agent_executions (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    agent_name VARCHAR(50),
    input_data JSONB,
    output_data JSONB,
    status VARCHAR(20),  -- running/success/failed
    error_message TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API 调用日志表
CREATE TABLE api_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    endpoint VARCHAR(100),
    method VARCHAR(10),
    status_code INTEGER,
    latency_ms INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引优化
CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_agent_executions_conversation ON agent_executions(conversation_id);
CREATE INDEX idx_api_logs_user_created ON api_logs(user_id, created_at);
```

### 2.2 Redis 缓存策略

```python
# 缓存 Key 设计
CACHE_KEYS = {
    # 用户会话缓存（TTL: 1小时）
    "session:{user_id}": {
        "ttl": 3600,
        "data": {
            "conversation_id": int,
            "message_history": list,
            "context": dict
        }
    },

    # 文档检索结果缓存（TTL: 30分钟）
    "search:{doc_id}:{query_hash}": {
        "ttl": 1800,
        "data": {
            "results": list,
            "timestamp": float
        }
    },

    # Agent 状态缓存（TTL: 2小时）
    "agent_state:{conversation_id}": {
        "ttl": 7200,
        "data": {
            "current_agent": str,
            "state": dict,
            "step_history": list
        }
    },

    # 限流计数器（TTL: 1分钟）
    "rate_limit:{user_id}:{endpoint}": {
        "ttl": 60,
        "data": {
            "count": int
        }
    }
}
```

---

## 🔌 三、API 设计

### 3.1 RESTful API 列表

#### 基础接口
```python
# 健康检查
GET /health

# 用户认证
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
```

#### RAG 知识库接口
```python
# 文档管理
POST   /api/v1/documents              # 上传文档
GET    /api/v1/documents              # 获取文档列表
GET    /api/v1/documents/{id}         # 获取文档详情
DELETE /api/v1/documents/{id}         # 删除文档

# RAG 问答
POST /api/v1/rag/query                # 智能问答
GET  /api/v1/rag/history              # 查询历史
```

#### 多 Agent 协作接口
```python
# 任务执行
POST /api/v1/agents/task              # 创建任务
GET  /api/v1/agents/task/{id}         # 查询任务状态
POST /api/v1/agents/task/{id}/cancel  # 取消任务

# 实时流式响应
WebSocket /ws/agents/task/{id}        # 实时进度推送
```

#### 对话管理接口
```python
# 会话管理
POST   /api/v1/conversations          # 创建会话
GET    /api/v1/conversations          # 获取会话列表
GET    /api/v1/conversations/{id}     # 获取会话详情
DELETE /api/v1/conversations/{id}     # 删除会话

# 消息管理
POST /api/v1/conversations/{id}/messages  # 发送消息
GET  /api/v1/conversations/{id}/messages  # 获取消息历史
```

### 3.2 WebSocket 协议设计

```python
# WebSocket 消息协议
{
    "type": "query" | "response" | "error" | "done",
    "data": {
        "content": str,
        "agent": str,              # 当前执行的 Agent
        "step": int,               # 执行步骤
        "metadata": dict
    }
}
```

---

## 🤖 四、Agent 设计

### 4.1 RAG Agent 架构

```python
from langgraph.graph import StateGraph
from typing import TypedDict

class RAGState(TypedDict):
    """RAG Agent 状态定义"""
    query: str                    # 用户查询
    retrieved_docs: list          # 检索到的文档
    context: str                  # 上下文
    answer: str                   # 生成的答案
    sources: list                 # 来源引用
    confidence: float             # 置信度

# RAG Agent 工作流
def build_rag_graph():
    graph = StateGraph(RAGState)

    # 添加节点
    graph.add_node("retrieve", retrieve_node)      # 检索节点
    graph.add_node("rerank", rerank_node)          # 重排序节点
    graph.add_node("generate", generate_node)      # 生成节点
    graph.add_node("verify", verify_node)          # 验证节点

    # 设置边
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", "verify")

    # 条件边：如果置信度低，重新检索
    graph.add_conditional_edges(
        "verify",
        should_retrieve,
        {
            "retrieve": "retrieve",
            "end": END
        }
    )

    return graph.compile()
```

### 4.2 Multi-Agent 协作架构

```python
class MultiAgentState(TypedDict):
    """多 Agent 协作状态"""
    task: str                     # 用户任务
    research_result: dict         # 研究结果
    code: str                     # 生成的代码
    review: dict                  # 审查结果
    final_output: dict            # 最终输出
    iteration: int                # 迭代次数

def build_multi_agent_graph():
    graph = StateGraph(MultiAgentState)

    # 添加 Agent 节点
    graph.add_node("manager", manager_node)       # 管理器 Agent
    graph.add_node("researcher", researcher_node) # 研究员 Agent
    graph.add_node("coder", coder_node)           # 程序员 Agent
    graph.add_node("reviewer", reviewer_node)     # 审查员 Agent

    # 设置工作流
    graph.set_entry_point("manager")

    # Manager 分配任务
    graph.add_conditional_edges(
        "manager",
        route_task,
        {
            "research": "researcher",
            "code": "coder",
            "end": END
        }
    )

    # 研究员 → 程序员
    graph.add_edge("researcher", "coder")

    # 程序员 → 审查员
    graph.add_edge("coder", "reviewer")

    # 审查员决策：通过或返工
    graph.add_conditional_edges(
        "reviewer",
        should_revise,
        {
            "coder": "coder",
            "end": END
        }
    )

    return graph.compile()
```

### 4.3 Agent 能力设计

| Agent | 能力 | 工具集 |
|-------|------|--------|
| **Researcher** | 信息检索、资料整理、需求分析 | Web Search, Wikipedia, Calculator |
| **Coder** | 代码生成、单元测试、代码优化 | Code Interpreter, File Write, Lint |
| **Reviewer** | 代码审查、安全检查、性能分析 | AST Parser, Security Scanner |
| **RAG Agent** | 文档检索、语义理解、答案生成 | Vector DB, Rerank API, LLM |

---

## ⚡ 五、关键技术实现

### 5.1 向量检索优化

```python
class HybridRetriever:
    """混合检索器：BM25 + 语义搜索"""

    def __init__(self):
        self.bm25 = BM25Retriever()
        self.vector = VectorRetriever()
        self.reranker = CohereReranker()

    async def retrieve(self, query: str, top_k: int = 10) -> list:
        # 1. 并行检索
        bm25_results, vector_results = await asyncio.gather(
            self.bm25.search(query, top_k * 2),
            self.vector.search(query, top_k * 2)
        )

        # 2. 结果融合（RRF 算法）
        combined = self.reciprocal_rank_fusion(
            bm25_results,
            vector_results
        )

        # 3. 重排序
        final_results = await self.reranker.rerank(
            query,
            combined[:top_k * 3],
            top_k=top_k
        )

        return final_results

    def reciprocal_rank_fusion(self, *result_lists, k=60):
        """RRF 融合算法"""
        scores = {}
        for results in result_lists:
            for rank, doc in enumerate(results):
                doc_id = doc['id']
                if doc_id not in scores:
                    scores[doc_id] = 0
                scores[doc_id] += 1 / (k + rank + 1)

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 5.2 流式响应实现

```python
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

async def stream_chat(
    query: str,
    conversation_id: int
) -> AsyncGenerator[str, None]:
    """流式聊天响应"""

    # 1. 保存用户消息
    await save_message(conversation_id, "user", query)

    # 2. 流式调用 LLM
    async for chunk in llm.stream(query):
        # 3. 实时推送给客户端
        yield f"data: {json.dumps({'content': chunk})}\n\n"

    # 4. 保存完整回复
    yield f"data: [DONE]\n\n"

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        stream_chat(request.query, request.conversation_id),
        media_type="text/event-stream"
    )
```

### 5.3 并发控制与限流

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/rag/query")
@limiter.limit("10/minute")  # 每分钟最多10次
async def rag_query(
    request: Request,
    query: QueryRequest
):
    # 信号量控制并发 LLM 调用
    semaphore = asyncio.Semaphore(5)  # 最多5个并发

    async with semaphore:
        result = await rag_service.query(query)
        return result
```

### 5.4 错误处理与降级

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMService:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def call_llm(self, prompt: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except RateLimitError:
            # 降级策略：切换到备用模型
            return await self._fallback_to_backup(prompt)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise
```

---

## 📦 六、目录结构（最终版）

```
AI_Smart_Gateway/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI 应用入口
│   │
│   ├── api/                         # Router 层
│   │   ├── __init__.py
│   │   ├── deps.py                  # 依赖注入
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py              # 认证接口
│   │       ├── documents.py         # 文档管理接口
│   │       ├── rag.py               # RAG 问答接口
│   │       ├── agents.py            # 多 Agent 接口
│   │       └── conversations.py     # 对话管理接口
│   │
│   ├── core/                        # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py                # 环境变量配置
│   │   ├── security.py              # 安全相关（JWT、密码加密）
│   │   └── logger.py                # 日志配置
│   │
│   ├── models/                      # 数据模型
│   │   ├── __init__.py
│   │   ├── database.py              # SQLAlchemy 模型
│   │   ├── schemas.py               # Pydantic Schema
│   │   └── enums.py                 # 枚举类型
│   │
│   ├── services/                    # Service 层
│   │   ├── __init__.py
│   │   ├── rag_service.py           # RAG 业务逻辑
│   │   ├── agent_service.py         # Agent 业务逻辑
│   │   ├── conversation_service.py  # 对话业务逻辑
│   │   └── document_service.py      # 文档业务逻辑
│   │
│   ├── agents/                      # Agent 层
│   │   ├── __init__.py
│   │   ├── base.py                  # Agent 基类
│   │   ├── rag_agent.py             # RAG Agent
│   │   ├── multi_agent_graph.py     # 多 Agent 编排
│   │   ├── tools/                   # Agent 工具集
│   │   │   ├── __init__.py
│   │   │   ├── search.py            # 搜索工具
│   │   │   ├── code.py              # 代码工具
│   │   │   └── file.py              # 文件工具
│   │   └── prompts/                 # Prompt 模板
│   │       ├── __init__.py
│   │       ├── rag_prompts.py
│   │       └── agent_prompts.py
│   │
│   ├── infrastructure/              # 基础设施层
│   │   ├── __init__.py
│   │   ├── database.py              # 数据库连接
│   │   ├── redis.py                 # Redis 连接
│   │   ├── vector_store.py          # 向量数据库
│   │   └── cache.py                 # 缓存管理
│   │
│   └── utils/                       # 工具函数
│       ├── __init__.py
│       ├── text_processing.py       # 文本处理
│       ├── retry.py                 # 重试机制
│       └── monitor.py               # 监控指标
│
├── tests/                           # 测试
│   ├── __init__.py
│   ├── test_api/
│   ├── test_services/
│   └── test_agents/
│
├── scripts/                         # 脚本
│   ├── init_db.py                   # 初始化数据库
│   └── seed_data.py                 # 填充测试数据
│
├── docs/                            # 文档
│   ├── TECH_DESIGN.md               # 技术设计文档
│   ├── API.md                       # API 文档
│   └── DEPLOYMENT.md                # 部署文档
│
├── main.py                          # 应用启动入口
├── requirements.txt                 # 依赖列表
├── .env.example                     # 环境变量模板
├── docker-compose.yml               # Docker 编排
├── Dockerfile                       # Docker 镜像
└── README.md                        # 项目说明
```

---

## 🚀 七、实施路线图

### Phase 1: 基础框架（Week 1）
- [x] 项目结构搭建
- [ ] 数据库初始化
- [ ] 基础 API 框架
- [ ] 认证系统
- [ ] 日志与监控

### Phase 2: RAG 系统（Week 2）
- [ ] 文档上传与解析
- [ ] 向量化与存储
- [ ] 混合检索实现
- [ ] RAG Agent 开发
- [ ] API 接口开发

### Phase 3: 多 Agent 系统（Week 3）
- [ ] Multi-Agent Graph 编排
- [ ] 研究员 Agent
- [ ] 程序员 Agent
- [ ] 审查员 Agent
- [ ] 流式响应实现

### Phase 4: 优化与部署（Week 4）
- [ ] 性能优化
- [ ] 缓存策略
- [ ] 错误处理
- [ ] Docker 部署
- [ ] 文档完善

---

## 💡 八、面试亮点总结

### 8.1 技术深度
1. **向量检索优化**：BM25 + 语义搜索混合检索，RRF 融合算法
2. **流式响应**：SSE 实时推送，提升用户体验
3. **并发控制**：信号量 + 限流，防止服务雪崩
4. **容错机制**：重试策略 + 降级方案，保证高可用

### 8.2 工程能力
1. **分层架构**：Router → Service → Agent 清晰分层
2. **异步编程**：全链路 async/await，提升并发性能
3. **缓存设计**：多级缓存策略，降低响应延迟
4. **监控告警**：日志 + 指标，便于问题排查

### 8.3 AI 能力
1. **LangGraph 编排**：复杂 Agent 工作流设计
2. **RAG 实战**：端到端知识库问答系统
3. **多 Agent 协作**：展示系统级 AI 应用能力
4. **Prompt 工程**：优化 Prompt 提升效果

---

**下一步**：从哪个模块开始开发？我建议先从 **Phase 1: 基础框架** 开始，打好基础再做上层功能。
