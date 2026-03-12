# 认证系统使用说明

## 🔐 认证机制说明

当前项目使用 **JWT（JSON Web Token）** 进行用户认证。

### 认证流程

```
1. 用户注册 → 创建账号
2. 用户登录 → 获取 Token
3. 携带 Token 访问受保护接口
4. 服务端验证 Token → 返回数据
```

---

## 📋 两种使用方案

### 方案1：启用认证（生产环境推荐）

#### 步骤1：注册用户

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "myuser",
    "email": "user@example.com",
    "password": "password123"
  }'
```

**响应**：
```json
{
  "success": true,
  "data": {
    "user": {
      "id": 1,
      "username": "myuser",
      "email": "user@example.com",
      "role": "user"
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "...",
      "token_type": "bearer",
      "expires_in": 1800
    }
  }
}
```

#### 步骤2：使用 Token

```bash
# 上传文档
curl -X POST "http://localhost:8000/api/v1/documents" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@document.txt"

# RAG 查询
curl -X POST "http://localhost:8000/api/v1/rag/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是人工智能？"}'
```

---

### 方案2：临时禁用认证（测试环境）

如果你只是想快速测试功能，可以暂时禁用认证：

#### 修改 `app/api/v1/documents.py`：

```python
# ❌ 原代码：需要认证
@router.post("/documents")
async def upload_document(
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):

# ✅ 修改后：使用可选认证
@router.post("/documents")
async def upload_document(
    current_user: Optional[User] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # 如果 current_user 为 None，使用默认用户
    if current_user is None:
        current_user = User(id=1, username="guest")  # 临时
```

#### 修改 `app/api/v1/rag.py`：

```python
# 同样的修改
@router.post("/rag/query")
async def rag_query(
    request: RAGQueryRequest,
    current_user: Optional[User] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # 如果 current_user 为 None，使用默认用户
    user_id = current_user.id if current_user else 1
    ...
```

---

## 🧪 快速测试认证

### 使用测试脚本

```bash
# 启动应用
python main.py

# 在另一个终端运行测试脚本
python scripts/test_auth.py
```

### 使用 Swagger UI

1. 访问 http://localhost:8000/docs
2. 找到 `POST /api/v1/auth/register`
3. 注册用户
4. 找到 `POST /api/v1/auth/login`
5. 登录获取 Token
6. 点击右上角 "Authorize" 按钮
7. 输入 `Bearer YOUR_TOKEN`
8. 现在可以访问所有受保护的接口

---

## 🔧 开发环境配置

### 环境变量

在 `.env` 文件中配置：

```bash
# JWT 密钥（生产环境必须修改！）
JWT_SECRET_KEY=your-secret-key-change-this
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### 测试用户

数据库初始化时会创建测试用户：
- 用户名：`testuser`
- 密码：`testpass123`
- 邮箱：`test@example.com`

---

## 🛡️ 安全建议

### 生产环境

1. **修改密钥**：生成强随机密钥
```python
import secrets
print(secrets.token_urlsafe(32))
```

2. **启用 HTTPS**：不要在生产环境使用 HTTP

3. **设置过期时间**：合理的 Token 过期时间

4. **刷新令牌**：实现刷新令牌机制

### 开发环境

- 可以使用较长的过期时间方便调试
- 使用简单的密钥
- 禁用 CORS 限制

---

## ❓ 常见问题

### Q: Token 过期了怎么办？

A: 重新登录获取新 Token，或者实现刷新令牌功能。

### Q: 如何实现"记住我"功能？

A: 使用 refresh_token，设置更长的过期时间。

### Q: 如何实现权限控制？

A: 在 `User` 模型中添加 `role` 字段，在接口中检查权限：
```python
if current_user.role != "admin":
    raise ForbiddenError("需要管理员权限")
```

### Q: 如何实现单点登录（SSO）？

A: 需要集成第三方认证服务（如 OAuth2、LDAP）。

---

## 📝 API 认证示例

### Python

```python
import httpx

async def upload_document(file_path: str, token: str):
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                "http://localhost:8000/api/v1/documents",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": f}
            )
    return response.json()
```

### JavaScript

```javascript
// 登录
const loginResponse = await fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        email: 'user@example.com',
        password: 'password123'
    })
});
const { data } = await loginResponse.json();
const token = data.tokens.access_token;

// 使用 Token
const response = await fetch('http://localhost:8000/api/v1/documents', {
    headers: {'Authorization': `Bearer ${token}`}
});
```

---

需要我帮你实现其他认证功能吗？
- [ ] 刷新令牌
- [ ] 忘记密码
- [ ] 邮箱验证
- [ ] OAuth2 集成
