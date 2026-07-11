"""Dify 白名单鉴权测试"""
import pytest


# ---------------------------------------------------------------------------
# 白名单接口列表
# ---------------------------------------------------------------------------

WHITELIST_ENDPOINTS = [
    ("GET", "/api/v1/courses"),
    ("GET", "/api/v1/events"),
    ("POST", "/api/v1/events/1/register"),
    ("POST", "/api/v1/dify/events/1/register"),
    ("POST", "/api/v1/chat/session"),
]

OPENAPI_WHITELIST_OPERATIONS = [
    ("get", "/api/v1/courses"),
    ("get", "/api/v1/events"),
    ("post", "/api/v1/events/{event_id}/register"),
    ("post", "/api/v1/dify/events/{event_id}/register"),
    ("post", "/api/v1/chat/session"),
]


class TestDifyAuth:
    """Dify Service Token 白名单鉴权"""

    @pytest.mark.parametrize("method,url", WHITELIST_ENDPOINTS)
    def test_correct_token_passes(self, client, auth_headers, seed_courses, seed_events, seed_user, method, url):
        """TC-AUTH001：正确 Token → 通过"""
        body = None
        if method == "POST":
            if "register" in url:
                body = {"user_id": 1001, "customer_name": "test", "contact_info": "138"}
            else:
                body = {}

        if body is not None:
            r = client.request(method, url, headers=auth_headers, json=body)
        else:
            r = client.request(method, url, headers=auth_headers)

        assert r.status_code != 403, f"{method} {url} should not return 403 with valid token"

    @pytest.mark.parametrize("method,url", WHITELIST_ENDPOINTS)
    def test_missing_auth_header(self, client, seed_courses, seed_events, method, url):
        """TC-AUTH002：缺少 Authorization Header → 403"""
        body = None
        if method == "POST":
            if "register" in url:
                body = {"user_id": 1001, "customer_name": "test", "contact_info": "138"}
            else:
                body = {}

        if body is not None:
            r = client.request(method, url, json=body)
        else:
            r = client.request(method, url)

        assert r.status_code == 403
        assert r.json()["code"] == 40301

    @pytest.mark.parametrize("method,url", WHITELIST_ENDPOINTS)
    def test_wrong_token(self, client, invalid_auth_headers, seed_courses, seed_events, method, url):
        """TC-AUTH003：错误 Token → 403"""
        body = None
        if method == "POST":
            if "register" in url:
                body = {"user_id": 1001, "customer_name": "test", "contact_info": "138"}
            else:
                body = {}

        if body is not None:
            r = client.request(method, url, headers=invalid_auth_headers, json=body)
        else:
            r = client.request(method, url, headers=invalid_auth_headers)

        assert r.status_code == 403
        assert r.json()["code"] == 40301

    @pytest.mark.parametrize("method,url", WHITELIST_ENDPOINTS)
    def test_non_bearer_format(self, client, seed_courses, seed_events, method, url):
        """TC-AUTH004：非 Bearer 格式 → 403"""
        body = None
        if method == "POST":
            if "register" in url:
                body = {"user_id": 1001, "customer_name": "test", "contact_info": "138"}
            else:
                body = {}

        if body is not None:
            r = client.request(method, url, headers={"Authorization": "Basic xxx"}, json=body)
        else:
            r = client.request(method, url, headers={"Authorization": "Basic xxx"})

        assert r.status_code == 403
        assert r.json()["code"] == 40301

    @pytest.mark.parametrize("method,url", WHITELIST_ENDPOINTS)
    def test_empty_token(self, client, seed_courses, seed_events, method, url):
        """TC-AUTH005：空 Token → 403"""
        body = None
        if method == "POST":
            if "register" in url:
                body = {"user_id": 1001, "customer_name": "test", "contact_info": "138"}
            else:
                body = {}

        if body is not None:
            r = client.request(method, url, headers={"Authorization": "Bearer "}, json=body)
        else:
            r = client.request(method, url, headers={"Authorization": "Bearer "})

        assert r.status_code == 403
        assert r.json()["code"] == 40301

    def test_missing_header_returns_403_not_422_with_query_params(self, client, seed_courses):
        """TC-AUTH006：缺失 Header + 正常查询参数 → 40301（非 422 原生 detail）

        回归：历史缺陷中 authorization 被声明为必填 Header，缺失时 FastAPI
        返回 422 + 原生 detail 数组，而非业务错误码 40301。修复后必须返回
        规范结构 {code, message, data} 且 HTTP 状态为 403。
        """
        url = "/api/v1/courses?min_price=0&max_price=2000&status=1&page=1&page_size=20"
        r = client.get(url)  # 无 Authorization
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
        body = r.json()
        # 规范结构断言：必须是 {code, message, data}，而非原生 detail 数组
        assert set(body.keys()) >= {"code", "message", "data"}
        assert body["code"] == 40301
        assert "detail" not in body

    def test_openapi_uses_bearer_security_scheme_for_whitelist(self, client):
        """Swagger 应使用 Bearer Authorize，不应把 Authorization 暴露为普通 header 输入框"""
        schema = client.get("/api/v1/openapi.json").json()
        security_schemes = schema["components"]["securitySchemes"]
        assert security_schemes["DifyServiceToken"]["scheme"] == "bearer"

        for method, path in OPENAPI_WHITELIST_OPERATIONS:
            operation = schema["paths"][path][method]
            assert {"DifyServiceToken": []} in operation.get("security", [])
            header_params = [
                param["name"].lower()
                for param in operation.get("parameters", [])
                if param.get("in") == "header"
            ]
            assert "authorization" not in header_params
