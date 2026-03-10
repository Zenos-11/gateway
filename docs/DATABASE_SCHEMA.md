# 数据库 Schema 详细设计

## PostgreSQL 数据模型

### 1. 用户表 (users)

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key_hash VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',  -- user/admin
    quota_used INTEGER DEFAULT 0,     -- 已使用配额
    quota_limit INTEGER DEFAULT 1000,  -- 配额限制
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_api_key ON users(api_key_hash);
```

### 2. 文档表 (documents)

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,  -- pdf/txt/md/docx
    file_size INTEGER,
    chunk_count INTEGER DEFAULT 0,
    vector_count INTEGER DEFAULT 0,
    processing_status VARCHAR(20) DEFAULT 'pending',
    -- pending/processing/completed/failed

    -- 文档元数据
    title VARCHAR(500),
    author VARCHAR(100),
    subject VARCHAR(200),
    keywords TEXT[],

    -- 性能指标
    indexing_time_ms INTEGER,

    metadata JSONB,  -- 灵活存储额外信息

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(processing_status);
CREATE INDEX idx_documents_type ON documents(file_type);

-- 全文搜索索引
CREATE INDEX idx_documents_content_gin ON documents USING gin(to_tsvector('english', title || ' ' || COALESCE(subject, '')));
```

### 3. 文档块表 (document_chunks)

```sql
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding_status VARCHAR(20) DEFAULT 'pending',
    -- pending/embedding/completed/failed

    -- 元数据
    page_number INTEGER,
    chunk_type VARCHAR(50),  -- text/code/table/image
    token_count INTEGER,

    -- 检索优化
    metadata JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_index ON document_chunks(document_id, chunk_index);

-- 全文搜索
CREATE INDEX idx_chunks_content_gin ON document_chunks USING gin(to_tsvector('english', content));
```

### 4. 向量数据表 (vectors)

```sql
-- 方案1: 使用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE vectors (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE CASCADE,
    embedding vector(1536),  -- OpenAI embedding dimension
    model_name VARCHAR(50) DEFAULT 'text-embedding-ada-002',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vectors_embedding ON vectors USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);

-- 方案2: 或者使用独立的向量数据库（如 ChromaDB）
-- 这个表仅存储引用
CREATE TABLE vector_references (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER REFERENCES document_chunks(id) ON DELETE CASCADE,
    vector_db_id VARCHAR(255),  -- ChromaDB/Pinecone ID
    vector_db_type VARCHAR(50),  -- chroma/pinecone/weaviate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5. 会话表 (conversations)

```sql
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    agent_type VARCHAR(50) NOT NULL,  -- rag/multi_agent/chat

    -- 模型配置
    model_name VARCHAR(50),
    temperature DECIMAL(3, 2),
    max_tokens INTEGER,

    -- Agent 配置
    agent_config JSONB,

    -- 统计信息
    message_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 4) DEFAULT 0,

    -- 状态
    status VARCHAR(20) DEFAULT 'active',  -- active/archived/deleted

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_type ON conversations(agent_type);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_created ON conversations(created_at DESC);
```

### 6. 消息表 (messages)

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- user/assistant/system/tool

    -- 内容
    content TEXT NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text',  -- text/image/code

    -- Token 统计
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,

    -- 性能指标
    latency_ms INTEGER,
    model_name VARCHAR(50),

    -- Agent 信息
    agent_name VARCHAR(50),
    tool_calls JSONB,

    -- 元数据
    metadata JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at DESC);
CREATE INDEX idx_messages_role ON messages(conversation_id, role);
```

### 7. Agent 执行记录表 (agent_executions)

```sql
CREATE TABLE agent_executions (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES messages(id),

    -- Agent 信息
    agent_name VARCHAR(50) NOT NULL,
    agent_type VARCHAR(50),  -- rag/researcher/coder/reviewer

    -- 输入输出
    input_data JSONB,
    output_data JSONB,

    -- 执行状态
    status VARCHAR(20) NOT NULL,  -- running/success/failed/cancelled
    error_message TEXT,
    error_stack TEXT,

    -- 性能指标
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    execution_time_ms INTEGER,

    -- 工具调用
    tools_used JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_executions_conversation ON agent_executions(conversation_id);
CREATE INDEX idx_agent_executions_message ON agent_executions(message_id);
CREATE INDEX idx_agent_executions_agent ON agent_executions(agent_name);
CREATE INDEX idx_agent_executions_status ON agent_executions(status);
CREATE INDEX idx_agent_executions_created ON agent_executions(created_at DESC);
```

### 8. 检索历史表 (retrieval_history)

```sql
CREATE TABLE retrieval_history (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    message_id INTEGER REFERENCES messages(id),
    user_id INTEGER REFERENCES users(id),

    -- 查询信息
    query_text TEXT NOT NULL,
    query_vector vector(1536),

    -- 检索配置
    retrieval_method VARCHAR(50),  -- semantic/hybrid/bm25
    top_k INTEGER,
    score_threshold DECIMAL(3, 2),

    -- 检索结果
    results JSONB,  -- 检索到的文档块
    result_count INTEGER,

    -- 性能指标
    retrieval_time_ms INTEGER,
    rerank_time_ms INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_retrieval_conversation ON retrieval_history(conversation_id);
CREATE INDEX idx_retrieval_user ON retrieval_history(user_id);
CREATE INDEX idx_retrieval_created ON retrieval_history(created_at DESC);
```

### 9. API 日志表 (api_logs)

```sql
CREATE TABLE api_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),

    -- 请求信息
    endpoint VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    path_params JSONB,
    query_params JSONB,
    body_params JSONB,

    -- 响应信息
    status_code INTEGER NOT NULL,
    response_body TEXT,

    -- 性能指标
    latency_ms INTEGER,
    db_query_count INTEGER,
    db_query_time_ms INTEGER,

    -- 客户端信息
    ip_address VARCHAR(45),
    user_agent TEXT,
    referer TEXT,

    -- 错误信息
    error_message TEXT,
    error_stack TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 分区表（按月分区）
CREATE TABLE api_logs_y2024m01 PARTITION OF api_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE INDEX idx_api_logs_user ON api_logs(user_id);
CREATE INDEX idx_api_logs_endpoint ON api_logs(endpoint);
CREATE INDEX idx_api_logs_status ON api_logs(status_code);
CREATE INDEX idx_api_logs_created ON api_logs(created_at DESC);

-- 时间序列自动清理
CREATE INDEX idx_api_logs_created_partition ON api_logs(created_at);
```

### 10. 系统配置表 (system_config)

```sql
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    value_type VARCHAR(20) DEFAULT 'string',  -- string/json/int/float/bool
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE,  -- 是否可以被前端访问
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 默认配置
INSERT INTO system_config (key, value, value_type, description, is_public) VALUES
('max_file_size', '10485760', 'int', '最大文件上传大小（字节）', FALSE),
('allowed_file_types', '["pdf","txt","md","docx"]', 'json', '允许的文件类型', TRUE),
('default_model', 'deepseek-v3', 'string', '默认模型', TRUE),
('max_conversation_length', '50', 'int', '最大对话轮次', FALSE),
('enable_rag_cache', 'true', 'bool', '启用 RAG 缓存', FALSE);
```

### 11. 用户反馈表 (user_feedback)

```sql
CREATE TABLE user_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    conversation_id INTEGER REFERENCES conversations(id),
    message_id INTEGER REFERENCES messages(id),

    -- 反馈类型
    feedback_type VARCHAR(20) NOT NULL,  -- thumbs_up/thumbs_down/flag
    rating INTEGER,  -- 1-5 星评分

    -- 详细反馈
    comment TEXT,
    category VARCHAR(50),  -- accuracy/relevance/safety/other

    -- Agent 信息
    agent_type VARCHAR(50),
    model_name VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_user ON user_feedback(user_id);
CREATE INDEX idx_feedback_conversation ON user_feedback(conversation_id);
CREATE INDEX idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX idx_feedback_created ON user_feedback(created_at DESC);
```

## Redis 数据结构设计

### 1. 会话缓存

```python
# Key: session:{user_id}:{conversation_id}
# Type: Hash
# TTL: 3600秒（1小时）

{
    "conversation_id": 123,
    "title": "关于RAG的讨论",
    "agent_type": "rag",
    "message_count": 10,
    "last_message_at": "2024-01-15T10:30:00Z",
    "context": {
        "current_topic": "RAG优化",
        "entities": ["LangGraph", "ChromaDB"],
        "summary": "用户询问了RAG系统的优化方法..."
    }
}
```

### 2. 检索结果缓存

```python
# Key: retrieval:{user_id}:{query_hash}
# Type: String (JSON)
# TTL: 1800秒（30分钟）

{
    "query": "什么是RAG",
    "results": [
        {
            "chunk_id": 456,
            "content": "RAG是检索增强生成...",
            "score": 0.95,
            "metadata": {...}
        }
    ],
    "retrieval_time_ms": 150,
    "cached_at": "2024-01-15T10:30:00Z"
}
```

### 3. Agent 状态缓存

```python
# Key: agent_state:{conversation_id}
# Type: Hash
# TTL: 7200秒（2小时）

{
    "current_agent": "coder",
    "state": {
        "task": "实现快速排序",
        "research_result": {...},
        "code": "def quicksort...",
        "iteration": 2
    },
    "step_history": [
        {"agent": "manager", "action": "分配任务", "timestamp": "..."},
        {"agent": "researcher", "action": "完成研究", "timestamp": "..."}
    ]
}
```

### 4. 限流计数器

```python
# Key: rate_limit:{user_id}:{endpoint}
# Type: String
# TTL: 60秒（1分钟）

"15"  # 请求次数
```

### 5. 在线用户列表

```python
# Key: online_users
# Type: Set
# TTL: 无（手动管理）

SADD online_users "user_123"
SADD online_users "user_456"

# 获取在线用户数
SCARD online_users

# 检查用户是否在线
SISMEMBER online_users "user_123"
```

### 6. 分布式锁

```python
# Key: lock:{resource_name}
# Type: String
# TTL: 30秒（自动过期）

SET lock:document_upload_123 "unique_lock_id" NX EX 30

# 释放锁
GET lock:document_upload_123
DEL lock:document_upload_123
```

## 数据库性能优化

### 1. 索引策略

```sql
-- 复合索引（最左前缀原则）
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at DESC);

-- 部分索引（只索引符合条件的行）
CREATE INDEX idx_active_conversations ON conversations(user_id, created_at DESC)
WHERE status = 'active';

-- 表达式索引
CREATE INDEX idx_documents_lower_filename ON documents(LOWER(filename));
```

### 2. 分区策略

```sql
-- 按时间分区（api_logs）
CREATE TABLE api_logs (
    -- ... 字段定义
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- 创建分区
CREATE TABLE api_logs_2024_01 PARTITION OF api_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### 3. 查询优化

```sql
-- 使用 EXPLAIN ANALYZE 分析查询
EXPLAIN ANALYZE
SELECT * FROM messages
WHERE conversation_id = 123
ORDER BY created_at DESC
LIMIT 20;

-- 使用连接池
-- SQLAlchemy 配置
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # 连接池大小
    max_overflow=40,       # 最大溢出连接数
    pool_pre_ping=True,    # 连接健康检查
    pool_recycle=3600      # 连接回收时间（秒）
)
```

### 4. 缓存策略

```python
# 多级缓存
L1_CACHE: 内存缓存（Python functools.lru_cache）
L2_CACHE: Redis 缓存
L3_CACHE: PostgreSQL 查询结果缓存

# 缓存预热
async def warmup_cache():
    # 预加载热点数据
    popular_docs = await db.execute(
        "SELECT * FROM documents ORDER BY created_at DESC LIMIT 100"
    )
    for doc in popular_docs:
        await redis.set(f"doc:{doc.id}", doc.json(), ex=3600)
```

---

**数据迁移脚本**：[scripts/migrate_database.py](../scripts/migrate_database.py)
**初始化脚本**：[scripts/init_db.py](../scripts/init_db.py)
