# AI Smart Gateway

> **基于 FastAPI + LangGraph 的企业级 AI 应用网关**
>
> [![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
> [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
> [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)

## 🎯 项目简介

AI Smart Gateway 是一个功能完备的 AI 应用网关，集成了 **RAG 智能问答** 和 **多 Agent 协作** 两大核心功能。该项目旨在展示如何使用 LangGraph 编排复杂 AI 工作流，适合作为简历项目和面试作品。

### ✨ 核心特性

- 🔍 **RAG 智能知识库**：支持 PDF/Word/Markdown 文档上传、向量化、智能问答
- 🤖 **多 Agent 协作**：研究员-程序员-审查员角色分工，自动完成复杂任务
- ⚡ **高性能架构**：全链路异步、多级缓存、流式响应
- 🛡️ **企业级工程**：认证授权、限流防护、监控告警、容器化部署

### 🏗️ 技术架构

```
客户端 (Web/Mobile/API)
    ↓
API Gateway (FastAPI + CORS + Rate Limiting)
    ↓
┌─────────────┬─────────────┬─────────────┐
│  RAG Agent  │ Multi-Agent │ Chat Agent  │
└─────────────┴─────────────┴─────────────┘
    ↓
┌─────────────┬─────────────┬─────────────┐
│ PostgreSQL  │   Redis     │  ChromaDB   │
└─────────────┴─────────────┴─────────────┘
```

## 📚 项目文档

- 📖 [技术设计文档](docs/TECH_DESIGN.md) - 系统架构、模块设计
- 🗄️ [数据库设计](docs/DATABASE_SCHEMA.md) - 数据模型、缓存策略
- 🔌 [API 接口文档](docs/API_DESIGN.md) - RESTful API、WebSocket 协议

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd langgraph_self_project

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key

# 3. 启动所有服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f app

# 5. 访问服务
# - API 文档：http://localhost:8000/docs
# - Grafana 监控：http://localhost:3000
# - Flower 监控：http://localhost:5555
```

### 方式二：本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动基础服务（PostgreSQL + Redis + ChromaDB）
docker-compose up -d postgres redis chromadb

# 4. 初始化数据库
python scripts/init_db.py

# 5. 启动应用
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔧 配置说明

### 环境变量

```bash
# ===== 数据库配置 =====
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_smart_gateway
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001

# ===== OpenAI API 配置 =====
OPENAI_API_KEY=sk-xxxxx
OPENAI_API_BASE=https://api.openai.com/v1
DEFAULT_MODEL=gpt-3.5-turbo

# ===== 应用配置 =====
APP_NAME=AI Smart Gateway
APP_VERSION=1.0.0
DEBUG=True
SECRET_KEY=your-secret-key-here

# ===== 限流配置 =====
RATE_LIMIT_ENABLED=True
RATE_LIMIT_PER_MINUTE=60

# ===== 文件上传配置 =====
MAX_FILE_SIZE=10485760  # 10MB
ALLOWED_FILE_TYPES=pdf,txt,md,docx
```

## 📖 核心功能演示

### 1. RAG 智能问答

```python
import requests

# 上传文档
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/documents",
        files={"file": f},
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
document_id = response.json()["data"]["id"]

# 智能问答
response = requests.post(
    "http://localhost:8000/api/v1/rag/query",
    json={
        "query": "文档中提到了哪些关键技术？",
        "top_k": 5
    },
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
answer = response.json()["data"]["answer"]
sources = response.json()["data"]["sources"]
```

### 2. 多 Agent 协作

```python
# 创建任务
response = requests.post(
    "http://localhost:8000/api/v1/agents/task",
    json={
        "task": "实现一个快速排序算法",
        "agents": ["researcher", "coder", "reviewer"]
    },
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
task_id = response.json()["data"]["task_id"]

# WebSocket 实时监控
import websocket
ws = websocket.create_connection(f"ws://localhost:8000/ws/agents/task/{task_id}")
while True:
    message = ws.recv()
    print(message)
```

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_api/test_rag.py

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

## 📊 监控与运维

### Prometheus 指标

访问 http://localhost:9090 查看以下指标：

- `http_requests_total` - HTTP 请求总数
- `http_request_duration_seconds` - 请求延迟
- `agent_executions_total` - Agent 执行总数
- `rag_queries_total` - RAG 查询总数

### Grafana 面板

访问 http://localhost:3000（默认账号：admin/admin）

### 日志

```bash
# 查看应用日志
docker-compose logs -f app

# 查看特定服务日志
docker-compose logs -f postgres
docker-compose logs -f celery_worker
```

## 🛠️ 技术栈

| 类别           | 技术                  | 用途                  |
| -------------- | --------------------- | --------------------- |
| **Web 框架**   | FastAPI               | 高性能异步 API        |
| **AI 编排**    | LangGraph             | 多 Agent 工作流       |
| **LLM 框架**   | LangChain             | LLM 抽象层            |
| **数据库**     | PostgreSQL + pgvector | 关系型数据 + 向量存储 |
| **缓存**       | Redis                 | 会话缓存、限流        |
| **向量数据库** | ChromaDB              | 文档向量存储          |
| **任务队列**   | Celery + Redis        | 异步任务处理          |
| **监控**       | Prometheus + Grafana  | 指标监控              |

## 📝 开发路线图

### Phase 1: 基础框架 ✅

- [x] 项目结构搭建
- [x] 数据库设计
- [x] 基础 API 框架
- [x] Docker 部署配置

### Phase 2: RAG 系统

- [ ] 文档上传与解析
- [ ] 向量化与存储
- [ ] 混合检索实现
- [ ] RAG Agent 开发

### Phase 3: 多 Agent 系统

- [ ] Multi-Agent Graph 编排
- [ ] 研究员 Agent
- [ ] 程序员 Agent
- [ ] 审查员 Agent

### Phase 4: 优化与部署

- [ ] 性能优化
- [ ] 缓存策略
- [ ] 错误处理
- [ ] 生产环境部署

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 License

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 💬 联系方式

- 项目主页：[GitHub Repository]
- 问题反馈：[Issues]
- 技术讨论：[Discussions]

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**
