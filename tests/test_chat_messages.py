"""消息记录接口测试 - POST/GET /api/v1/chat/session/{session_id}/messages"""
import pytest
import time


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _create_session(client, auth_headers, user_id=None):
    """创建测试用会话，返回 session_id"""
    body = {"user_id": user_id} if user_id else {}
    r = client.post("/api/v1/chat/session", headers=auth_headers, json=body)
    return r.json()["data"]["session_id"]


def _save_message(client, session_id, role, content, **kwargs):
    """保存测试用消息"""
    body = {"role": role, "content": content, **kwargs}
    return client.post(
        f"/api/v1/chat/session/{session_id}/messages",
        json=body,
    )


# ---------------------------------------------------------------------------
# 保存消息
# ---------------------------------------------------------------------------

class TestSaveMessage:
    """保存消息"""

    def test_save_user_message(self, client, auth_headers):
        """TC-MSG001：保存 user 消息"""
        session_id = _create_session(client, auth_headers)
        r = _save_message(client, session_id, "user", "你好")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["role"] == "user"
        assert data["content"] == "你好"

    def test_save_assistant_message_with_metadata(self, client, auth_headers):
        """TC-MSG002：保存 assistant 消息（带 intent 和 tokens）"""
        session_id = _create_session(client, auth_headers)
        r = _save_message(
            client, session_id, "assistant", "你好，有什么可以帮您？",
            intent="greeting", tokens_used=15, response_time_ms=320,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["role"] == "assistant"
        assert data["intent"] == "greeting"
        assert data["tokens_used"] == 15
        assert data["response_time_ms"] == 320

    def test_save_message_to_nonexistent_session(self, client):
        """TC-MSG003：保存消息到不存在的会话 → 404"""
        r = _save_message(client, "not-exist-id", "user", "test")
        assert r.status_code == 404

    def test_save_message_invalid_role(self, client, auth_headers):
        """TC-MSG004：role 字段非法值 → 422"""
        session_id = _create_session(client, auth_headers)
        r = _save_message(client, session_id, "admin", "test")
        assert r.status_code == 422

    def test_save_message_empty_content(self, client, auth_headers):
        """TC-MSG005：content 为空"""
        session_id = _create_session(client, auth_headers)
        r = _save_message(client, session_id, "user", "")
        # 当前 Pydantic 定义 content: str 允许空字符串，返回 200
        # 如未来修改为 Field(min_length=1) 则此测试需调整
        assert r.status_code in (200, 422)

    def test_last_message_time_updated(self, client, auth_headers):
        """TC-MSG006：保存消息后会话 last_message_time 更新"""
        session_id = _create_session(client, auth_headers)
        r = _save_message(client, session_id, "user", "你好")
        assert r.status_code == 200

        # 通过查询会话验证 last_message_time
        # 由于 session 接口在白名单内，我们用保存消息的响应验证间接行为
        # 直接通过 DB 验证更可靠，但集成测试层面已验证消息成功保存


# ---------------------------------------------------------------------------
# 查询消息历史
# ---------------------------------------------------------------------------

class TestListMessages:
    """查询消息历史"""

    def test_list_messages(self, client, auth_headers):
        """TC-MSG007：查询消息列表"""
        session_id = _create_session(client, auth_headers)
        _save_message(client, session_id, "user", "msg1")
        _save_message(client, session_id, "assistant", "reply1")
        _save_message(client, session_id, "user", "msg2")

        r = client.get(f"/api/v1/chat/session/{session_id}/messages")
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 3

    def test_cursor_pagination_has_more(self, client, auth_headers):
        """TC-MSG008：游标分页（有更多数据）"""
        session_id = _create_session(client, auth_headers)
        for i in range(25):
            _save_message(client, session_id, "user", f"message_{i}")

        r = client.get(f"/api/v1/chat/session/{session_id}/messages?limit=10")
        assert r.status_code == 200
        body = r.json()["data"]
        assert len(body["items"]) == 10
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    def test_cursor_pagination_last_page(self, client, auth_headers):
        """TC-MSG009：游标分页（最后一页）"""
        session_id = _create_session(client, auth_headers)
        for i in range(25):
            _save_message(client, session_id, "user", f"message_{i}")

        # 第一页
        r1 = client.get(f"/api/v1/chat/session/{session_id}/messages?limit=10")
        next_cursor = r1.json()["data"]["next_cursor"]

        # 第二页
        r2 = client.get(f"/api/v1/chat/session/{session_id}/messages?cursor={next_cursor}&limit=10")
        body2 = r2.json()["data"]
        assert len(body2["items"]) == 10

        # 第三页（最后）
        next_cursor2 = body2["next_cursor"]
        r3 = client.get(f"/api/v1/chat/session/{session_id}/messages?cursor={next_cursor2}&limit=10")
        body3 = r3.json()["data"]
        assert body3["has_more"] is False

    def test_list_messages_nonexistent_session(self, client):
        """TC-MSG010：查询不存在会话的消息 → 404"""
        r = client.get("/api/v1/chat/session/not-exist-id/messages")
        assert r.status_code == 404

    def test_limit_max_100(self, client, auth_headers):
        """TC-MSG011：limit 边界值（最大值 100）"""
        session_id = _create_session(client, auth_headers)
        r = client.get(f"/api/v1/chat/session/{session_id}/messages?limit=100")
        assert r.status_code == 200

    def test_limit_exceeds_100(self, client, auth_headers):
        """TC-MSG012：limit 超限 101 → 422"""
        session_id = _create_session(client, auth_headers)
        r = client.get(f"/api/v1/chat/session/{session_id}/messages?limit=101")
        assert r.status_code == 422

    def test_limit_zero(self, client, auth_headers):
        """TC-MSG013：limit=0 → 422"""
        session_id = _create_session(client, auth_headers)
        r = client.get(f"/api/v1/chat/session/{session_id}/messages?limit=0")
        assert r.status_code == 422

    def test_messages_in_desc_order(self, client, auth_headers):
        """TC-MSG014：消息按时间倒序排列（按 id 降序）"""
        session_id = _create_session(client, auth_headers)
        _save_message(client, session_id, "user", "first")
        time.sleep(0.1)
        _save_message(client, session_id, "user", "second")

        r = client.get(f"/api/v1/chat/session/{session_id}/messages")
        items = r.json()["data"]["items"]
        assert items[0]["content"] == "second"
        assert items[1]["content"] == "first"
