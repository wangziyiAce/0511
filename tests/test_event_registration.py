"""活动报名接口测试 - POST/DELETE /api/v1/events/{event_id}/register"""
import pytest
import threading
from models.chat import EventLecture


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _register(client, event_id, user_id, auth_headers):
    """封装报名请求"""
    return client.post(
        f"/api/v1/events/{event_id}/register",
        headers=auth_headers,
        json={
            "user_id": user_id,
            "customer_name": f"测试用户{user_id}",
            "contact_info": f"13800{user_id:05d}",
        },
    )


def _dify_register(client, event_id, user_id, auth_headers):
    """POST through the Dify-compatible registration endpoint."""
    return client.post(
        f"/api/v1/dify/events/{event_id}/register",
        headers=auth_headers,
        json={
            "user_id": user_id,
            "customer_name": f"test-user-{user_id}",
            "contact_info": f"13800{user_id:05d}",
        },
    )


def _register_guest(client, event_id, contact_info, auth_headers, use_dify_endpoint=False):
    """Register a visitor without user_id, matching Dify's event_register body."""
    url = (
        f"/api/v1/dify/events/{event_id}/register"
        if use_dify_endpoint
        else f"/api/v1/events/{event_id}/register"
    )
    return client.post(
        url,
        headers=auth_headers,
        json={
            "user_id": None,
            "customer_name": "guest-user",
            "contact_info": contact_info,
        },
    )


# ---------------------------------------------------------------------------
# 正常报名
# ---------------------------------------------------------------------------

class TestEventRegistration:
    """活动报名"""

    def test_normal_register(self, client, auth_headers, seed_events, seed_user):
        """TC-REG001：正常报名（user_id=1001）"""
        r = _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["event_id"] == 1
        assert data["status"] == "registered"

    def test_participants_increment_after_register(self, client, auth_headers, seed_events, seed_user, db_session):
        """TC-REG002：报名后 current_participants +1"""
        # 报名前
        event_before = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        before_count = event_before.current_participants

        r = _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 200

        # 报名后
        db_session.expire_all()
        event_after = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        assert event_after.current_participants == before_count + 1

    def test_duplicate_registration(self, client, auth_headers, seed_events, seed_user):
        """TC-REG003：同一用户重复报名 → 409"""
        # 第一次报名
        r1 = _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r1.status_code == 200

        # 第二次报名（同一用户）
        r2 = _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r2.status_code == 409
        body = r2.json()
        assert body["code"] == 40901
        assert "已报名" in body["message"]

    def test_dify_duplicate_registration_returns_200_with_business_code(
        self, client, auth_headers, seed_events, seed_user
    ):
        """Dify repeat registration should continue workflow with code=40901."""
        r1 = _dify_register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json()["code"] == 0

        r2 = _dify_register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r2.status_code == 200
        body = r2.json()
        assert body["code"] == 40901
        assert body["data"] is None

    def test_dify_duplicate_guest_contact_returns_200_with_business_code(
        self, client, auth_headers, seed_events
    ):
        """Dify visitor repeat registration should map contact conflicts to code=40901."""
        contact_info = "13800138000"
        r1 = _register_guest(
            client, event_id=1, contact_info=contact_info, auth_headers=auth_headers, use_dify_endpoint=True
        )
        assert r1.status_code == 200
        assert r1.json()["code"] == 0

        r2 = _register_guest(
            client, event_id=1, contact_info=contact_info, auth_headers=auth_headers, use_dify_endpoint=True
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["code"] == 40901
        assert body["data"] is None

    def test_duplicate_guest_contact_returns_409_on_rest_endpoint(
        self, client, auth_headers, seed_events
    ):
        """The REST endpoint should keep HTTP 409 for duplicate visitor contact."""
        contact_info = "13800138001"
        r1 = _register_guest(client, event_id=1, contact_info=contact_info, auth_headers=auth_headers)
        assert r1.status_code == 200

        r2 = _register_guest(client, event_id=1, contact_info=contact_info, auth_headers=auth_headers)
        assert r2.status_code == 409
        assert r2.json()["code"] == 40901

    def test_dify_register_non_existing_event_returns_200_with_business_code(
        self, client, auth_headers, seed_user
    ):
        """Dify missing event should continue workflow with code=40401."""
        r = _dify_register(client, event_id=99999, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["code"] == 40401

    def test_register_non_existing_event(self, client, auth_headers, seed_user):
        """TC-REG004：报名不存在的活动 → 404"""
        r = _register(client, event_id=99999, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 404
        assert r.json()["code"] == 40401

    def test_register_ended_event(self, client, auth_headers, db_session, seed_user):
        """TC-REG005：报名已结束的活动 → 422"""
        from models.chat import EventLecture
        ended_event = EventLecture(
            event_name="已结束活动", event_type="online",
            description="test", start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=10, current_participants=0, status="ended"
        )
        db_session.add(ended_event)
        db_session.commit()

        r = _register(client, event_id=ended_event.id, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 422
        assert r.json()["code"] == 40902

    def test_dify_register_ended_event_returns_200_with_business_code(
        self, client, auth_headers, db_session, seed_user
    ):
        """Dify unavailable event should continue workflow with code=40902."""
        ended_event = EventLecture(
            event_name="ended event",
            event_type="online",
            description="test",
            start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=10,
            current_participants=0,
            status="ended",
        )
        db_session.add(ended_event)
        db_session.commit()

        r = _dify_register(client, event_id=ended_event.id, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["code"] == 40902

    def test_register_cancelled_event(self, client, auth_headers, db_session, seed_user):
        """TC-REG006：报名已取消的活动 → 422"""
        cancelled_event = EventLecture(
            event_name="已取消活动", event_type="online",
            description="test", start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=10, current_participants=0, status="cancelled"
        )
        db_session.add(cancelled_event)
        db_session.commit()

        r = _register(client, event_id=cancelled_event.id, user_id=1001, auth_headers=auth_headers)
        assert r.status_code == 422
        assert r.json()["code"] == 40902

    def test_register_nonexistent_user(self, client, auth_headers, seed_events):
        """TC-REG007：user_id 逻辑外键校验 → 404"""
        r = _register(client, event_id=1, user_id=99999, auth_headers=auth_headers)
        assert r.status_code == 404
        assert r.json()["code"] == 40402

    def test_missing_auth_header(self, client, seed_events, seed_user):
        """TC-REG008：不带 Authorization Header → 403"""
        r = client.post(
            "/api/v1/events/1/register",
            json={"user_id": 1001, "customer_name": "张三", "contact_info": "13800138000"},
        )
        assert r.status_code == 403
        assert r.json()["code"] == 40301

    def test_register_full_capacity(self, client, auth_headers, db_session, seed_user):
        """TC-REG009：报名名额已满 → 422"""
        from models.user import SysUser
        full_event = EventLecture(
            event_name="满额活动", event_type="online",
            description="test", start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=1, current_participants=1, status="upcoming"
        )
        db_session.add(full_event)
        # 创建额外用户
        user2 = SysUser(id=1002, username="user2", password_hash="x", role="student", status=1)
        db_session.add(user2)
        db_session.commit()

        r = _register(client, event_id=full_event.id, user_id=1002, auth_headers=auth_headers)
        assert r.status_code == 422
        assert r.json()["code"] == 40902
        assert "名额已满" in r.json()["message"]

    def test_concurrent_registration(self, client, auth_headers, db_session, seed_multiple_users):
        """TC-REG010：并发报名（5 线程抢 1 个名额）"""
        # 创建名额=1的活动
        one_spot_event = EventLecture(
            event_name="抢名额活动", event_type="online",
            description="test", start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=1, current_participants=0, status="upcoming"
        )
        db_session.add(one_spot_event)
        db_session.commit()
        event_id = one_spot_event.id

        results = []
        lock = threading.Lock()

        def do_register(user_id):
            # 每个线程用独立 client（共享同一个 db_session fixture 回滚后会有问题，这里用新的）
            from fastapi.testclient import TestClient
            from main import app
            from utils.database import get_db
            # 为每个线程创建独立的 DB 连接
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
            from utils.database import Base
            # 注意：此测试需要数据库在内存中且已建表，实际由 fixtures 保证
            # 简化：用相同的 client 但注意 SQLite 锁

            try:
                r = _register(client, event_id, user_id, auth_headers)
                with lock:
                    results.append((user_id, r.status_code))
            except Exception as e:
                with lock:
                    results.append((user_id, f"error:{e}"))

        threads = []
        for i in range(2001, 2006):  # 5 个用户
            t = threading.Thread(target=do_register, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证：只有 1 人成功
        success_count = sum(1 for _, code in results if code == 200)
        fail_count = sum(1 for _, code in results if code in (422, 409))
        assert success_count == 1, f"Expected 1 success, got {success_count}. Results: {results}"
        assert fail_count == 4, f"Expected 4 failures, got {fail_count}. Results: {results}"


# ---------------------------------------------------------------------------
# 取消报名
# ---------------------------------------------------------------------------

class TestCancelRegistration:
    """取消报名"""

    def test_normal_cancel(self, client, auth_headers, seed_events, seed_user):
        """TC-REG011：正常取消报名"""
        # 先报名
        r1 = _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        assert r1.status_code == 200

        # 取消报名
        r2 = client.delete("/api/v1/events/1/register?user_id=1001")
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "cancelled"

    def test_participants_decrement_after_cancel(self, client, auth_headers, seed_events, seed_user, db_session):
        """TC-REG012：取消后 current_participants -1"""
        # 先报名
        _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)

        db_session.expire_all()
        event_before = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        before_count = event_before.current_participants

        # 取消
        client.delete("/api/v1/events/1/register?user_id=1001")

        db_session.expire_all()
        event_after = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        assert event_after.current_participants == before_count - 1

    def test_cancel_non_existing_registration(self, client, seed_events):
        """TC-REG013：取消不存在的报名记录 → 404"""
        r = client.delete("/api/v1/events/1/register?user_id=99999")
        assert r.status_code == 404

    def test_duplicate_cancel(self, client, auth_headers, seed_events, seed_user):
        """TC-REG014：重复取消 → 404"""
        # 先报名
        _register(client, event_id=1, user_id=1001, auth_headers=auth_headers)
        # 取消
        client.delete("/api/v1/events/1/register?user_id=1001")
        # 再次取消
        r = client.delete("/api/v1/events/1/register?user_id=1001")
        assert r.status_code == 404
        assert "不存在" in r.json()["message"] or "已取消" in r.json()["message"]
