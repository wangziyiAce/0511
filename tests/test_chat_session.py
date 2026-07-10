"""会话管理接口测试 - POST /api/v1/chat/session"""
import pytest


class TestCreateSession:
    """创建/获取会话"""

    def test_create_session_without_user_id(self, client, auth_headers):
        """TC-S001：创建新会话（无 user_id）"""
        r = client.post("/api/v1/chat/session", headers=auth_headers, json={})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["session_id"].startswith("cs_")
        assert data["status"] == "active"

    def test_create_session_with_visitor_info(self, client, auth_headers):
        """TC-S002：创建新会话（带 visitor 信息）"""
        r = client.post(
            "/api/v1/chat/session",
            headers=auth_headers,
            json={"visitor_name": "李四", "visitor_contact": "13900139000"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["visitor_name"] == "李四"
        assert data["visitor_contact"] == "13900139000"

    def test_same_user_returns_existing_active_session(self, client, auth_headers):
        """TC-S003：同一 user_id 返回已有活跃会话"""
        # 第一次创建
        r1 = client.post(
            "/api/v1/chat/session",
            headers=auth_headers,
            json={"user_id": 1001},
        )
        assert r1.status_code == 200
        session_id_1 = r1.json()["data"]["session_id"]

        # 第二次创建（同一 user_id）
        r2 = client.post(
            "/api/v1/chat/session",
            headers=auth_headers,
            json={"user_id": 1001},
        )
        assert r2.status_code == 200
        session_id_2 = r2.json()["data"]["session_id"]

        assert session_id_1 == session_id_2

    def test_different_users_create_different_sessions(self, client, auth_headers):
        """TC-S004：不同 user_id 创建不同会话"""
        r1 = client.post("/api/v1/chat/session", headers=auth_headers, json={"user_id": 1001})
        r2 = client.post("/api/v1/chat/session", headers=auth_headers, json={"user_id": 1002})
        assert r1.json()["data"]["session_id"] != r2.json()["data"]["session_id"]

    def test_missing_auth_header(self, client):
        """TC-S005：不带 Authorization Header → 403"""
        r = client.post("/api/v1/chat/session", json={})
        assert r.status_code == 403
        assert r.json()["code"] == 40301

    def test_invalid_token(self, client, invalid_auth_headers):
        """TC-S006：无效 Authorization Token → 403"""
        r = client.post("/api/v1/chat/session", headers=invalid_auth_headers, json={})
        assert r.status_code == 403
        assert r.json()["code"] == 40301
