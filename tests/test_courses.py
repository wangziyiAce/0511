"""课程查询接口测试 - GET /api/v1/courses, GET /api/v1/courses/{course_id}"""
import pytest


class TestListCourses:
    """课程列表查询"""

    # ------------------------------------------------------------------
    # 正常场景
    # ------------------------------------------------------------------

    def test_default_returns_all_active(self, client, auth_headers, seed_courses):
        """TC-C001：默认查询返回所有上架课程"""
        r = client.get("/api/v1/courses", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 10
        assert len(body["data"]["items"]) == 10

    def test_filter_by_category_language(self, client, auth_headers, seed_courses):
        """TC-C002：按 category=语言培训 筛选"""
        r = client.get("/api/v1/courses?category=语言培训", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["total"] == 4
        for item in body["data"]["items"]:
            assert item["category"] == "语言培训"

    def test_filter_by_category_background(self, client, auth_headers, seed_courses):
        """TC-C003：按 category=背景提升 筛选"""
        r = client.get("/api/v1/courses?category=背景提升", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 3

    def test_filter_by_category_study_abroad(self, client, auth_headers, seed_courses):
        """TC-C004：按 category=留学申请 筛选"""
        r = client.get("/api/v1/courses?category=留学申请", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 3

    def test_filter_by_keyword_match(self, client, auth_headers, seed_courses):
        """TC-C005：按 keyword=雅思 搜索"""
        r = client.get("/api/v1/courses?keyword=雅思", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["total"] >= 1
        for item in body["data"]["items"]:
            assert "雅思" in item["project_name"]

    def test_filter_by_keyword_no_match(self, client, auth_headers, seed_courses):
        """TC-C006：按 keyword=不存在的关键词"""
        r = client.get("/api/v1/courses?keyword=火星移民", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_filter_by_min_price(self, client, auth_headers, seed_courses):
        """TC-C007：按 min_price=10000 筛选"""
        r = client.get("/api/v1/courses?min_price=10000", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            assert item["price"] >= 10000

    def test_filter_by_max_price(self, client, auth_headers, seed_courses):
        """TC-C008：按 max_price=10000 筛选"""
        r = client.get("/api/v1/courses?max_price=10000", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            assert item["price"] <= 10000

    def test_combined_filter(self, client, auth_headers, seed_courses):
        """TC-C009：组合筛选 category + keyword"""
        r = client.get("/api/v1/courses?category=语言培训&keyword=托福", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    # ------------------------------------------------------------------
    # 分页
    # ------------------------------------------------------------------

    def test_pagination_page1_size3(self, client, auth_headers, seed_courses):
        """TC-C010：分页 page=1, page_size=3"""
        r = client.get("/api/v1/courses?page=1&page_size=3", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]["items"]) == 3
        assert body["data"]["page"] == 1
        assert body["data"]["page_size"] == 3

    def test_pagination_page2_size3(self, client, auth_headers, seed_courses):
        """TC-C011：分页 page=2, page_size=3"""
        r = client.get("/api/v1/courses?page=2&page_size=3", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["total"] == 10
        assert len(body["data"]["items"]) == 3

    def test_pagination_page_size_max_100(self, client, auth_headers, seed_courses):
        """TC-C012：分页 page_size 边界值 le=100"""
        r = client.get("/api/v1/courses?page_size=100", headers=auth_headers)
        assert r.status_code == 200

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------

    def test_page_size_exceeds_100(self, client, auth_headers, seed_courses):
        """TC-C013：分页 page_size 超限 101 → 422"""
        r = client.get("/api/v1/courses?page_size=101", headers=auth_headers)
        assert r.status_code == 422

    def test_page_size_zero(self, client, auth_headers, seed_courses):
        """TC-C014：分页 page_size=0 → 422"""
        r = client.get("/api/v1/courses?page_size=0", headers=auth_headers)
        assert r.status_code == 422

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    def test_missing_auth_header(self, client, seed_courses):
        """TC-C015：不带 Authorization Header → 403"""
        r = client.get("/api/v1/courses")
        assert r.status_code == 403
        assert r.json()["code"] == 40301


class TestGetCourse:
    """课程详情查询"""

    def test_existing_course(self, client, seed_courses):
        """TC-C016：查询存在的课程"""
        r = client.get("/api/v1/courses/1")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == 1
        assert data["project_name"] is not None

    def test_non_existing_course(self, client, seed_courses):
        """TC-C017：查询不存在的课程 → 404"""
        r = client.get("/api/v1/courses/99999")
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == 40401
        assert "课程不存在" in body["message"]

    def test_non_numeric_id(self, client, seed_courses):
        """TC-C018：查询非数字 ID → 422"""
        r = client.get("/api/v1/courses/abc")
        assert r.status_code == 422
