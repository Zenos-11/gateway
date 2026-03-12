# RAG 系统测试指南

## 🚀 快速启动

### 1. 启动所有服务

```bash
# 启动 PostgreSQL + Redis + ChromaDB
docker-compose up -d postgres redis chromadb

# 等待服务就绪...
sleep 5

# 初始化数据库
python scripts/init_db.py

# 启动应用
python main.py
```

### 2. 验证服务状态

访问以下地址验证服务：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

---

## 📝 测试流程

### 步骤1：创建测试文档

创建一个简单的测试文档 `test_doc.txt`：

```txt
人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，
它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。

该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
人工智能从诞生以来，理论和技术日益成熟，应用领域也不断扩大。

机器学习是人工智能的一个子集，它使用算法来解析数据、从中学习，
然后对现实世界中的事件做出决策或预测。
深度学习是机器学习的一种方法，它使用多层神经网络从大量数据中学习。
```

### 步骤2：上传文档

**方式一：使用 Swagger UI**
1. 访问 http://localhost:8000/docs
2. 找到 `POST /api/v1/documents` 接口
3. 点击 "Try it out"
4. 上传刚才创建的 `test_doc.txt`
5. 点击 "Execute"

**方式二：使用 curl**
```bash
# 注意：需要先登录获取 token（如果实现了认证）
curl -X POST "http://localhost:8000/api/v1/documents" \
  -F "file=@test_doc.txt" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**预期响应**：
```json
{
  "success": true,
  "data": {
    "id": 1,
    "filename": "test_doc.txt",
    "file_type": "txt",
    "file_size": 245,
    "chunk_count": 3,
    "status": "completed",
    "created_at": "2024-01-15T10:30:00"
  }
}
```

### 步骤3：查询文档列表

```bash
curl -X GET "http://localhost:8000/api/v1/documents" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 步骤4：RAG 智能问答

**方式一：使用 Swagger UI**
1. 在 API 文档中找到 `POST /api/v1/rag/query`
2. 点击 "Try it out"
3. 输入查询：
```json
{
  "query": "什么是人工智能？"
}
```
4. 点击 "Execute"

**方式二：使用 curl**
```bash
curl -X POST "http://localhost:8000/api/v1/rag/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "什么是人工智能？",
    "top_k": 3
  }'
```

**预期响应**：
```json
{
  "success": true,
  "data": {
    "answer": "人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。",
    "sources": [
      {
        "content": "人工智能（Artificial Intelligence，简称AI）是...",
        "metadata": {
          "document_id": 1,
          "chunk_id": 1,
          "filename": "test_doc.txt"
        },
        "score": 0.23
      }
    ],
    "confidence": 0.77,
    "performance": {
      "retrieval_time_ms": 150,
      "generation_time_ms": 1200,
      "total_time_ms": 1350
    }
  }
}
```

---

## 🔍 调试技巧

### 查看日志

```bash
# 实时查看应用日志
tail -f logs/app.log

# 查看错误日志
tail -f logs/error.log
```

### 检查向量存储

```bash
# 进入 ChromaDB 容器
docker exec -it ai_smart_gateway_chromadb bash

# 使用 Python 检查
python3 <<EOF
import chromadb
client = chromadb.HttpClient(host="localhost", port=8000)
collection = client.get_collection("documents")
print(f"文档数量: {collection.count()}")
EOF
```

### 检查数据库

```bash
# 连接数据库
docker exec -it ai_smart_gateway_db psql -U postgres -d ai_smart_gateway

# 查询文档
SELECT id, filename, file_type, chunk_count, processing_status
FROM documents
ORDER BY created_at DESC;

# 查询文档块
SELECT id, document_id, chunk_index, LENGTH(content) as content_length
FROM document_chunks
ORDER BY document_id, chunk_index;
```

---

## 🐛 常见问题

### 问题1：文档上传失败

**错误信息**：`不支持的文件类型`

**解决方法**：
- 检查文件扩展名是否在 `ALLOWED_FILE_TYPES` 中
- 确认文件不是伪装的（如 .txt 实际是 .pdf）

### 问题2：向量化失败

**错误信息**：`ChromaDB 连接失败`

**解决方法**：
```bash
# 检查 ChromaDB 是否运行
docker ps | grep chroma

# 重启 ChromaDB
docker-compose restart chromadb
```

### 问题3：RAG 查询无结果

**错误信息**：`未找到相关文档`

**解决方法**：
1. 确认文档已成功上传（status=completed）
2. 检查向量存储中是否有数据
3. 尝试降低 `score_threshold` 或增加 `top_k`

### 问题4：LLM 调用失败

**错误信息**：`LLM 调用失败`

**解决方法**：
1. 检查 `.env` 中的 `OPENAI_API_KEY` 是否正确
2. 确认 `OPENAI_API_BASE` URL 可访问
3. 检查 API 配额是否充足

---

## 📊 性能优化建议

### 1. 文档分块优化

```python
# 调整分块大小和重叠
chunks_data = await chunk_document(
    text_content,
    chunker_type="recursive",
    chunk_size=1000,  # 根据文档类型调整
    chunk_overlap=200,  # 增加重叠可提高召回率
)
```

### 2. 检索参数优化

```python
# 调整检索数量和阈值
result = await rag_service.query(
    query_text=query,
    top_k=10,  # 增加检索数量
    score_threshold=0.5,  # 降低阈值
)
```

### 3. 使用缓存

```python
# Redis 缓存常见问题
cache_key = f"rag:{hash(query)}"
cached = await redis.get(cache_key)
if cached:
    return json.loads(cached)
```

---

## ✅ 测试检查清单

- [ ] 文档上传成功（status=completed）
- [ ] 文档分块正确（chunk_count > 0）
- [ ] 向量化完成（vector_count = chunk_count）
- [ ] 检索返回相关文档
- [ ] 答案基于文档内容
- [ ] 来源引用正确
- [ ] 性能指标正常（< 5秒）

---

## 🎯 下一步

- [ ] 实现用户认证
- [ ] 添加流式响应
- [ ] 实现多轮对话
- [ ] 优化检索算法（混合检索、重排序）
- [ ] 添加文档管理功能（编辑、删除）
