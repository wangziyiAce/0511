"""应用层数据一致性测试 - 逻辑外键、事务、并发"""
import pytest
import threading
from models.chat import EventLecture, EventRegistration


class TestDataConsistency:
    """数据一致性验证"""

    def test_user_logical_fk_check(self, client, auth_headers, seed_events):
        """TC-DC001：报名时 user_id 逻辑外键校验"""
        r = client.post(
            "/api/v1/events/1/register",
            headers=auth_headers,
            json={"user_id": 99999, "customer_name": "不存在用户", "contact_info": "138"},
        )
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == 40402
        assert "用户不存在" in body["message"]

    def test_event_logical_fk_check(self, client, auth_headers, seed_user):
        """TC-DC002：报名时 event_id 逻辑外键校验"""
        r = client.post(
            "/api/v1/events/99999/register",
            headers=auth_headers,
            json={"user_id": 1001, "customer_name": "test", "contact_info": "138"},
        )
        assert r.status_code == 404
        assert r.json()["code"] == 40401

    def test_message_session_logical_fk_check(self, client):
        """TC-DC003：保存消息时 session_id 逻辑外键校验"""
        r = client.post(
            "/api/v1/chat/session/not-exist-session/messages",
            json={"role": "user", "content": "test"},
        )
        assert r.status_code == 404

    def test_registration_transaction_atomicity(self, client, auth_headers, seed_events, seed_user, db_session):
        """TC-DC004：报名事务原子性 - 重复报名不改变名额"""
        # 第一次报名
        r1 = client.post(
            "/api/v1/events/1/register",
            headers=auth_headers,
            json={"user_id": 1001, "customer_name": "test", "contact_info": "138"},
        )
        assert r1.status_code == 200

        db_session.expire_all()
        event_after_first = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        count_after_first = event_after_first.current_participants

        # 重复报名（应失败并回滚）
        r2 = client.post(
            "/api/v1/events/1/register",
            headers=auth_headers,
            json={"user_id": 1001, "customer_name": "test", "contact_info": "138"},
        )
        assert r2.status_code == 409

        # 名额不应变化
        db_session.expire_all()
        event_after_dup = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        assert event_after_dup.current_participants == count_after_first

    def test_cancel_restores_capacity(self, client, auth_headers, seed_events, seed_user, db_session):
        """TC-DC005：取消报名后名额恢复"""
        # 报名
        client.post(
            "/api/v1/events/1/register",
            headers=auth_headers,
            json={"user_id": 1001, "customer_name": "test", "contact_info": "138"},
        )

        db_session.expire_all()
        event_before = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        before_count = event_before.current_participants

        # 取消
        r = client.delete("/api/v1/events/1/register?user_id=1001")
        assert r.status_code == 200

        db_session.expire_all()
        event_after = db_session.query(EventLecture).filter(EventLecture.id == 1).first()
        assert event_after.current_participants == before_count - 1

    def test_concurrent_capacity_accuracy(self, client, auth_headers, db_session, seed_multiple_users):
        """TC-DC006：并发报名名额计数准确性"""
        # 创建名额=5的活动
        event = EventLecture(
            event_name="并发容量测试", event_type="online",
            description="test", start_time="2026-01-01 10:00:00",
            end_time="2026-01-01 12:00:00",
            max_participants=5, current_participants=0, status="upcoming"
        )
        db_session.add(event)
        db_session.commit()
        event_id = event.id

        results = []
        lock = threading.Lock()

        def do_register(user_id):
            try:
                r = client.post(
                    f"/api/v1/events/{event_id}/register",
                    headers=auth_headers,
                    json={
                        "user_id": user_id,
                        "customer_name": f"用户{user_id}",
                        "contact_info": f"138{user_id:05d}",
                    },
                )
                with lock:
                    results.append(r.status_code)
            except Exception:
                with lock:
                    results.append(500)

        threads = []
        # 10 个用户同时报名（名额只有 5 个）
        for uid in range(2001, 2011):
            t = threading.Thread(target=do_register, args=(uid,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for c in results if c == 200)
        # 应有 5 人成功（因为名额=5）
        assert success_count == 5, f"Expected 5 successes, got {success_count}. Results: {results}"

        # 验证数据库中的报名人数
        db_session.expire_all()
        event_final = db_session.query(EventLecture).filter(EventLecture.id == event_id).first()
        assert event_final.current_participants == 5

        # 验证报名记录数
        reg_count = db_session.query(EventRegistration).filter(
            EventRegistration.event_id == event_id,
            EventRegistration.status == "registered",
        ).count()
        assert reg_count == 5
