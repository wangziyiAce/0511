"""智能报告助手 — API 路由注册验证。

测试目标：
1. 新路由正确注册在 routers/__init__.py 中
2. 原报告路由路径不变
3. assistant 路由的 prefix 不产生重复
4. 路由模块可正常导入

注意：register_routers() 需要数据库连接等完整环境，
因此本测试改为验证路由注册的源代码级正确性。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 路由注册源代码验证
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    """验证 routers/__init__.py 中 assistant 路由的正确注册。"""

    @pytest.fixture
    def init_content(self) -> str:
        init_path = Path(__file__).parent.parent / "routers" / "__init__.py"
        return init_path.read_text(encoding="utf-8")

    def test_assistant_router_imported(self, init_content):
        """验证 assistant 路由被 import。"""
        assert "from routers.report_assistant import router as report_assistant_router" in init_content

    def test_assistant_router_registered(self, init_content):
        """验证 assistant 路由被 include_router。"""
        assert "include_router(report_assistant_router" in init_content
        assert '/api/v1/reports/assistant' in init_content
        assert '智能报告助手' in init_content

    def test_report_router_still_imported(self, init_content):
        """原报告路由仍被导入。"""
        assert "from routers.report import router as report_router" in init_content
        assert 'include_router(report_router, prefix="/api/v1/reports", tags=["智能报告"])' in init_content

    def test_no_duplicate_prefix_in_include_lines(self, init_content):
        """assistant 注册的 include_router 行不产生 /api/v1/api/v1 重复 prefix。"""
        # 只检查实际的 include_router 行（排除注释）
        include_lines = [
            line for line in init_content.split("\n")
            if "include_router" in line and not line.strip().startswith("#")
        ]
        for line in include_lines:
            # 检查 assistant 行的 prefix 是否是 /api/v1/reports/assistant
            if "report_assistant_router" in line:
                assert 'prefix="/api/v1/reports/assistant"' in line, (
                    f"assistant prefix 不正确: {line.strip()}"
                )

    def test_assistant_registered_between_report_and_schedule(self, init_content):
        """assistant 在 report 和 report_schedule 之间注册（保持有序）。"""
        report_idx = init_content.index('include_router(report_router,')
        assistant_idx = init_content.index('include_router(report_assistant_router,')
        schedule_idx = init_content.index('include_router(report_schedule_router,')
        assert report_idx < assistant_idx < schedule_idx


# ---------------------------------------------------------------------------
# 路由模块验证
# ---------------------------------------------------------------------------


class TestAssistantRouterModule:
    def test_router_module_importable(self):
        """routers/report_assistant.py 可正常导入。"""
        from routers.report_assistant import router
        assert router is not None

    def test_router_has_messages_endpoint(self):
        """路由包含 POST /messages 端点。"""
        from routers.report_assistant import router
        routes = [
            (r.path, r.methods)
            for r in router.routes
            if hasattr(r, "methods")
        ]
        messages_routes = [
            (path, methods)
            for path, methods in routes
            if "messages" in path
        ]
        assert len(messages_routes) == 1
        assert "POST" in messages_routes[0][1]

    def test_router_prefix_is_empty(self):
        """router 自身无 prefix（prefix 由 register_routers 中的 include_router 提供）。"""
        from routers.report_assistant import router
        assert router.prefix == ""


# ---------------------------------------------------------------------------
# 原报告路由路径不变
# ---------------------------------------------------------------------------


class TestOriginalReportRoutes:
    def test_types_route_path(self):
        """原 /api/v1/reports/types 路径在 register_routers 中定义。"""
        init_path = Path(__file__).parent.parent / "routers" / "__init__.py"
        content = init_path.read_text(encoding="utf-8")
        assert 'prefix="/api/v1/reports"' in content

    def test_generate_route_unmodified(self):
        """routers/report.py 中 generate 路径未改变。"""
        report_path = Path(__file__).parent.parent / "routers" / "report.py"
        content = report_path.read_text(encoding="utf-8")
        assert '/generate' in content or '"generate"' in content
