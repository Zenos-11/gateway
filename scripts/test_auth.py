"""
认证系统测试脚本
演示如何注册、登录、使用 Token
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient
from app.core.config import settings


async def test_auth():
    """测试认证流程"""
    base_url = f"http://localhost:{settings.APP_CONFIG.get('port', 8000)}"

    print("=" * 60)
    print("🧪 认证系统测试")
    print("=" * 60)

    async with AsyncClient(base_url=base_url) as client:
        # ===== 1. 注册新用户 =====
        print("\n1️⃣ 注册新用户...")
        register_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123"
        }

        try:
            response = await client.post("/api/v1/auth/register", json=register_data)
            if response.status_code == 200:
                print("✅ 注册成功")
            else:
                print(f"⚠️ 注册失败: {response.text}")
        except Exception as e:
            print(f"⚠️ 注册异常: {e}")

        # ===== 2. 登录 =====
        print("\n2️⃣ 用户登录...")
        login_data = {
            "email": "test@example.com",
            "password": "testpass123"
        }

        response = await client.post("/api/v1/auth/login", json=login_data)
        if response.status_code == 200:
            data = response.json()["data"]
            access_token = data["tokens"]["access_token"]
            print("✅ 登录成功")
            print(f"   用户: {data['user']['username']}")
            print(f"   Token: {access_token[:50]}...")
        else:
            print(f"❌ 登录失败: {response.text}")
            return

        # ===== 3. 使用 Token 访问受保护接口 =====
        print("\n3️⃣ 使用 Token 访问受保护接口...")
        headers = {"Authorization": f"Bearer {access_token}"}

        # 获取用户信息
        response = await client.get("/api/v1/auth/me", headers=headers)
        if response.status_code == 200:
            user_data = response.json()["data"]
            print("✅ 获取用户信息成功")
            print(f"   用户名: {user_data['username']}")
            print(f"   配额: {user_data['quota_used']}/{user_data['quota_limit']}")
        else:
            print(f"❌ 获取用户信息失败: {response.text}")

        # 获取文档列表
        response = await client.get("/api/v1/documents", headers=headers)
        if response.status_code == 200:
            print("✅ 获取文档列表成功")
            print(f"   文档数: {len(response.json()['data']['items'])}")
        else:
            print(f"❌ 获取文档列表失败: {response.text}")

    print("\n" + "=" * 60)
    print("🎉 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_auth())
