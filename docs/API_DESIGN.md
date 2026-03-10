# API 接口设计文档

## 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
- **认证方式**: JWT Bearer Token
- **响应格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

### 成功响应

```json
{
    "success": true,
    "data": {},
    "message": "操作成功",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### 错误响应

```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "参数验证失败",
        "details": []
    },
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### 分页响应

```json
{
    "success": true,
    "data": {
        "items": [],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 100,
            "pages": 5
        }
    }
}
```

---

## 1. 认证模块

### 1.1 用户注册

```http
POST /auth/register
```

**请求体**：
```json
{
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePass123!"
}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "user": {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "created_at": "2024-01-15T10:30:00Z"
        },
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
}
```

### 1.2 用户登录

```http
POST /auth/login
```

**请求体**：
```json
{
    "email": "test@example.com",
    "password": "SecurePass123!"
}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "user": {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com"
        },
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
}
```

### 1.3 获取当前用户信息

```http
GET /auth/me
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "quota_used": 150,
        "quota_limit": 1000,
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

---

## 2. 文档管理模块

### 2.1 上传文档

```http
POST /documents
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**请求参数**：
- `file`: 文件（必需）
- `title`: 文档标题（可选）
- `author`: 作者（可选）
- `keywords`: 关键词，逗号分隔（可选）

**响应**：
```json
{
    "success": true,
    "data": {
        "id": 123,
        "filename": "example.pdf",
        "file_type": "pdf",
        "file_size": 1024000,
        "status": "processing",
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

### 2.2 获取文档列表

```http
GET /documents?page=1&page_size=20&status=completed&file_type=pdf
Authorization: Bearer {token}
```

**查询参数**：
- `page`: 页码（默认1）
- `page_size`: 每页数量（默认20）
- `status`: 状态筛选（pending/processing/completed/failed）
- `file_type`: 文件类型筛选
- `search`: 搜索关键词

**响应**：
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": 123,
                "filename": "example.pdf",
                "title": "RAG系统设计",
                "file_type": "pdf",
                "file_size": 1024000,
                "chunk_count": 50,
                "status": "completed",
                "created_at": "2024-01-15T10:30:00Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 45,
            "pages": 3
        }
    }
}
```

### 2.3 获取文档详情

```http
GET /documents/{id}
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "id": 123,
        "filename": "example.pdf",
        "title": "RAG系统设计",
        "author": "张三",
        "keywords": ["RAG", "LangGraph", "向量检索"],
        "file_type": "pdf",
        "file_size": 1024000,
        "chunk_count": 50,
        "vector_count": 150,
        "status": "completed",
        "indexing_time_ms": 2500,
        "metadata": {},
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

### 2.4 删除文档

```http
DELETE /documents/{id}
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "message": "文档已删除"
}
```

### 2.5 获取文档块列表

```http
GET /documents/{id}/chunks?page=1&page_size=20
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": 456,
                "chunk_index": 0,
                "content": "RAG系统是结合了检索和生成的AI系统...",
                "page_number": 1,
                "token_count": 256,
                "metadata": {}
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 50,
            "pages": 3
        }
    }
}
```

---

## 3. RAG 问答模块

### 3.1 智能问答

```http
POST /rag/query
Authorization: Bearer {token}
```

**请求体**：
```json
{
    "query": "什么是RAG系统？",
    "conversation_id": 789,  // 可选，用于多轮对话
    "retrieval_config": {
        "top_k": 5,
        "score_threshold": 0.7,
        "method": "hybrid"  // semantic/hybrid/bm25
    },
    "generation_config": {
        "model": "deepseek-v3",
        "temperature": 0.7,
        "max_tokens": 1000
    },
    "stream": false
}
```

**响应（非流式）**：
```json
{
    "success": true,
    "data": {
        "conversation_id": 789,
        "message_id": 101112,
        "answer": "RAG（Retrieval-Augmented Generation）系统是结合了检索和生成的AI系统...",
        "sources": [
            {
                "chunk_id": 456,
                "document_id": 123,
                "content": "RAG系统是...",
                "score": 0.95,
                "metadata": {
                    "filename": "example.pdf",
                    "page_number": 1
                }
            }
        ],
        "confidence": 0.92,
        "tokens_used": {
            "prompt_tokens": 500,
            "completion_tokens": 300,
            "total_tokens": 800
        },
        "latency_ms": 1500
    }
}
```

**响应（流式）**：
```
data: {"type": "start", "data": {"conversation_id": 789}}

data: {"type": "retrieval", "data": {"status": "retrieving", "progress": 0.5}}

data: {"type": "chunk", "data": {"content": "RAG"}}

data: {"type": "chunk", "data": {"content": "系统"}}

...

data: {"type": "sources", "data": {"sources": [...]}}

data: {"type": "end", "data": {"latency_ms": 1500, "tokens_used": {...}}}
```

### 3.2 获取查询历史

```http
GET /rag/history?conversation_id=789&page=1&page_size=20
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": 101112,
                "query": "什么是RAG系统？",
                "answer": "RAG（Retrieval-Augmented Generation）...",
                "sources": [...],
                "confidence": 0.92,
                "created_at": "2024-01-15T10:30:00Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 10,
            "pages": 1
        }
    }
}
```

### 3.3 反馈

```http
POST /rag/feedback
Authorization: Bearer {token}
```

**请求体**：
```json
{
    "message_id": 101112,
    "feedback_type": "thumbs_up",  // thumbs_up/thumbs_down/flag
    "rating": 5,  // 1-5星
    "comment": "回答很有帮助",
    "category": "accuracy"
}
```

**响应**：
```json
{
    "success": true,
    "message": "反馈已提交"
}
```

---

## 4. 多 Agent 协作模块

### 4.1 创建任务

```http
POST /agents/task
Authorization: Bearer {token}
```

**请求体**：
```json
{
    "task": "实现一个快速排序算法，并编写单元测试",
    "agent_config": {
        "agents": ["researcher", "coder", "reviewer"],
        "max_iterations": 3,
        "timeout": 300
    },
    "conversation_id": 789,
    "stream": true
}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "task_id": "task_abc123",
        "status": "running",
        "current_agent": "researcher",
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

### 4.2 查询任务状态

```http
GET /agents/task/{task_id}
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "task_id": "task_abc123",
        "status": "running",  // running/completed/failed/cancelled
        "progress": 0.6,
        "current_agent": "coder",
        "step_history": [
            {
                "agent": "researcher",
                "action": "完成研究",
                "output": "快速排序是一种高效的排序算法...",
                "timestamp": "2024-01-15T10:30:00Z"
            },
            {
                "agent": "coder",
                "action": "生成代码",
                "output": "正在生成代码...",
                "timestamp": "2024-01-15T10:31:00Z"
            }
        ],
        "elapsed_time_ms": 60000
    }
}
```

### 4.3 取消任务

```http
POST /agents/task/{task_id}/cancel
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "message": "任务已取消"
}
```

### 4.4 WebSocket 实时推送

```javascript
// 客户端连接
const ws = new WebSocket('ws://localhost:8000/ws/agents/task/task_abc123');

// 监听消息
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch(data.type) {
        case 'start':
            console.log('任务开始');
            break;
        case 'agent_start':
            console.log(`Agent ${data.data.agent} 开始执行`);
            break;
        case 'agent_end':
            console.log(`Agent ${data.data.agent} 执行完成`, data.data.output);
            break;
        case 'progress':
            console.log(`进度: ${data.data.progress}%`);
            break;
        case 'error':
            console.error('错误:', data.data.error);
            break;
        case 'end':
            console.log('任务完成', data.data.result);
            break;
    }
};
```

---

## 5. 对话管理模块

### 5.1 创建会话

```http
POST /conversations
Authorization: Bearer {token}
```

**请求体**：
```json
{
    "title": "讨论RAG优化",
    "agent_type": "rag",  // rag/multi_agent/chat
    "model_config": {
        "model": "deepseek-v3",
        "temperature": 0.7,
        "max_tokens": 1000
    },
    "agent_config": {}
}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "id": 789,
        "title": "讨论RAG优化",
        "agent_type": "rag",
        "model_name": "deepseek-v3",
        "message_count": 0,
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

### 5.2 获取会话列表

```http
GET /conversations?agent_type=rag&status=active&page=1&page_size=20
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": 789,
                "title": "讨论RAG优化",
                "agent_type": "rag",
                "message_count": 10,
                "total_tokens": 5000,
                "updated_at": "2024-01-15T10:30:00Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 5,
            "pages": 1
        }
    }
}
```

### 5.3 获取会话详情

```http
GET /conversations/{id}
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "id": 789,
        "title": "讨论RAG优化",
        "agent_type": "rag",
        "model_name": "deepseek-v3",
        "temperature": 0.7,
        "message_count": 10,
        "total_tokens": 5000,
        "total_cost": 0.05,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
    }
}
```

### 5.4 删除会话

```http
DELETE /conversations/{id}
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "message": "会话已删除"
}
```

### 5.5 发送消息

```http
POST /conversations/{id}/messages
Authorization: Bearer {token}
```

**请求体**：
```json
{
    "content": "你好，请介绍一下RAG系统",
    "stream": false
}
```

**响应（非流式）**：
```json
{
    "success": true,
    "data": {
        "user_message": {
            "id": 101112,
            "role": "user",
            "content": "你好，请介绍一下RAG系统",
            "created_at": "2024-01-15T10:30:00Z"
        },
        "assistant_message": {
            "id": 101113,
            "role": "assistant",
            "content": "RAG系统是...",
            "tokens_used": {
                "prompt_tokens": 50,
                "completion_tokens": 200,
                "total_tokens": 250
            },
            "latency_ms": 1200,
            "created_at": "2024-01-15T10:30:01Z"
        }
    }
}
```

**响应（流式）**：
```
data: {"type": "message_start", "data": {"message_id": 101113}}

data: {"type": "content_delta", "data": {"delta": "RAG"}}

data: {"type": "content_delta", "data": {"delta": "系统"}}

...

data: {"type": "message_end", "data": {"tokens_used": {...}, "latency_ms": 1200}}
```

### 5.6 获取消息历史

```http
GET /conversations/{id}/messages?page=1&page_size=20
Authorization: Bearer {token}
```

**响应**：
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": 101112,
                "role": "user",
                "content": "你好，请介绍一下RAG系统",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "id": 101113,
                "role": "assistant",
                "content": "RAG系统是...",
                "tokens_used": {...},
                "latency_ms": 1200,
                "created_at": "2024-01-15T10:30:01Z"
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 10,
            "pages": 1
        }
    }
}
```

---

## 6. 系统配置模块

### 6.1 获取系统配置

```http
GET /system/config
```

**响应**：
```json
{
    "success": true,
    "data": {
        "max_file_size": 10485760,
        "allowed_file_types": ["pdf", "txt", "md", "docx"],
        "default_model": "deepseek-v3",
        "max_conversation_length": 50,
        "features": {
            "rag_enabled": true,
            "multi_agent_enabled": true,
            "stream_enabled": true
        }
    }
}
```

### 6.2 获取系统状态

```http
GET /system/health
```

**响应**：
```json
{
    "success": true,
    "data": {
        "status": "healthy",
        "version": "1.0.0",
        "uptime": 86400,
        "services": {
            "database": "healthy",
            "redis": "healthy",
            "vector_db": "healthy",
            "llm": "healthy"
        },
        "metrics": {
            "active_conversations": 150,
            "requests_per_minute": 500,
            "average_latency_ms": 800
        }
    }
}
```

---

## 7. 错误码说明

| 错误码 | 说明 |
|--------|------|
| `VALIDATION_ERROR` | 参数验证失败 |
| `UNAUTHORIZED` | 未授权 |
| `FORBIDDEN` | 无权限 |
| `NOT_FOUND` | 资源不存在 |
| `RATE_LIMIT_EXCEEDED` | 超出速率限制 |
| `QUOTA_EXCEEDED` | 超出配额 |
| `INTERNAL_ERROR` | 服务器内部错误 |
| `SERVICE_UNAVAILABLE` | 服务不可用 |
| `INVALID_FILE_TYPE` | 不支持的文件类型 |
| `FILE_TOO_LARGE` | 文件过大 |
| `DOCUMENT_PROCESSING_FAILED` | 文档处理失败 |
| `AGENT_EXECUTION_FAILED` | Agent 执行失败 |
| `LLM_ERROR` | LLM 调用失败 |

---

## 8. 限流规则

| 端点类型 | 限制 |
|---------|------|
| 认证接口 | 10次/分钟 |
| 文档上传 | 5次/分钟 |
| RAG 查询 | 20次/分钟 |
| 多 Agent 任务 | 5次/分钟 |
| 其他接口 | 60次/分钟 |

---

## 9. WebSocket 连接

### 连接端点

```
ws://localhost:8000/ws/agents/task/{task_id}
```

### 心跳机制

```javascript
// 每30秒发送一次心跳
setInterval(() => {
    ws.send(JSON.stringify({ type: 'ping' }));
}, 30000);
```

### 重连策略

```javascript
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

ws.onclose = () => {
    if (reconnectAttempts < maxReconnectAttempts) {
        setTimeout(() => {
            reconnectAttempts++;
            ws reconnect();
        }, 1000 * Math.pow(2, reconnectAttempts));  // 指数退避
    }
};
```

---

## 10. SDK 使用示例

### Python SDK

```python
from ai_smart_gateway import Client

# 初始化客户端
client = Client(api_key="your-api-key", base_url="http://localhost:8000")

# RAG 问答
result = client.rag.query(
    query="什么是RAG？",
    top_k=5,
    stream=False
)
print(result.answer)

# 多 Agent 任务
task = client.agents.create_task(
    task="实现快速排序",
    agents=["researcher", "coder", "reviewer"]
)

# 监听任务进度
for event in task.stream_events():
    print(f"[{event.agent}] {event.output}")
```

### JavaScript SDK

```javascript
import { Client } from 'ai-smart-gateway';

const client = new Client({
    apiKey: 'your-api-key',
    baseURL: 'http://localhost:8000'
});

// RAG 问答
const result = await client.rag.query({
    query: '什么是RAG？',
    topK: 5
});
console.log(result.answer);

// 流式响应
for await (const chunk of client.rag.queryStream({
    query: '什么是RAG？'
})) {
    console.log(chunk.content);
}
```

---

**Postman Collection**: [docs/api_collection.json](./api_collection.json)
**OpenAPI Spec**: [docs/openapi.yaml](./openapi.yaml)
