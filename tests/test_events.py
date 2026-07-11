"""活动查询接口测试 - GET /api/v1/events, GET /api/v1/events/{event_id}"""
import pytest


class TestListEvents:
    """活动列表查询"""

    # ------------------------------------------------------------------
    # 正常场景
    # ------------------------------------------------------------------

    def test_default_returns_all_upcoming(self, client, auth_headers, seed_events):
        """TC-E001：默认查询返回所有 upcoming 活动"""
        r = client.get("/api/v1/events", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 5

    def test_filter_by_type_online(self, client, auth_headers, seed_events):
        """TC-E002：按 event_type=online 筛选"""
        r = client.get("/api/v1/events?event_type=online", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            assert item["event_type"] == "online"

    def test_filter_by_type_offline(self, client, auth_headers, seed_events):
        """TC-E003：按 event_type=offline 筛选"""
        r = client.get("/api/v1/events?event_type=offline", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_filter_by_type_hybrid(self, client, auth_headers, seed_events):
        """TC-E004：按 event_type=hybrid 筛选"""
        r = client.get("/api/v1/events?event_type=hybrid", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_filter_by_status_upcoming(self, client, auth_headers, seed_events):
        """TC-E005：按 status=upcoming 筛选"""
        r = client.get("/api/v1/events?status=upcoming", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 5

    def test_filter_by_status_ongoing_empty(self, client, auth_headers, seed_events):
        """TC-E006：按 status=ongoing 筛选（无数据）"""
        r = client.get("/api/v1/events?status=ongoing", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    # ------------------------------------------------------------------
    # 分页
    # ------------------------------------------------------------------

    def test_pagination_page1_size2(self, client, auth_headers, seed_events):
        """TC-E007：分页 page=1, page_size=2"""
        r = client.get("/api/v1/events?page=1&page_size=2", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 2

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    def test_missing_auth_header(self, client, seed_events):
        """TC-E008：不带 Authorization Header → 403"""
        r = client.get("/api/v1/events")
        assert r.status_code == 403
        assert r.json()["code"] == 40301

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------

    def test_page_size_exceeds_100(self, client, auth_headers, seed_events):
        """page_size 超限 101 → 422"""
        r = client.get("/api/v1/events?page_size=101", headers=auth_headers)
        assert r.status_code == 422


class TestGetEvent:
    """活动详情查询"""

    def test_existing_event(self, client, seed_events):
        """TC-E009：查询存在的活动"""
        r = client.get("/api/v1/events/1")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == 1
        assert data["event_name"] is not None

    def test_non_existing_event(self, client, seed_events):
        """TC-E010：查询不存在的活动 → 404"""
        r = client.get("/api/v1/events/99999")
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == 40401
        assert "活动不存在" in body["message"]
