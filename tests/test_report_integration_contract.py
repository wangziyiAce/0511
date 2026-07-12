"""智能报告集成契约测试。

本文件位于测试层，用于冻结智能报告模块交付给前端和团队集成时的公开契约。
上游由 pytest 执行，下游读取真实 FastAPI OpenAPI、前端 operation catalog、
环境变量示例和导出的 JSON 文件。测试失败时应先检查路由注册、Schema 或前端路径，
不能为了让文档通过而静默修改已经冻结的业务行为。
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_SNAPSHOT = PROJECT_ROOT / "docs" / "integration" / "openapi-iteration3.json"

FROZEN_REPORT_PATHS = {
    "/api/v1/report-actions/{action_id}",
    "/api/v1/report-data/application-materials",
    "/api/v1/report-data/channel-costs",
    "/api/v1/report-data/contracts",
    "/api/v1/report-data/payments",
    "/api/v1/report-schedules",
    "/api/v1/report-schedules/{schedule_id}",
    "/api/v1/reports",
    "/api/v1/reports/actions/{action_id}",
    "/api/v1/reports/assistant/messages",
    "/api/v1/reports/generate",
    "/api/v1/reports/types",
    "/api/v1/reports/{report_id}",
    "/api/v1/reports/{report_id}/actions",
    "/api/v1/reports/{report_id}/retry",
}


def test_exported_openapi_matches_real_fastapi_application() -> None:
    """验证冻结文件来自真实应用，避免手写 JSON 与运行时接口逐渐分叉。"""

    assert OPENAPI_SNAPSHOT.exists(), "必须先从 main.app 导出冻结版 OpenAPI"
    exported_schema = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert exported_schema == app.openapi()


def test_frozen_report_paths_exist_and_operation_ids_are_unique() -> None:
    """验证核心报告路径完整且 operationId 唯一，供前端稳定生成调用契约。"""

    schema = app.openapi()
    assert FROZEN_REPORT_PATHS <= set(schema["paths"])

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_frontend_operation_catalog_covers_frozen_report_paths() -> None:
    """验证统一前端登记报告路径，避免后端存在接口但演示页面没有调用入口。"""

    catalog = (
        PROJECT_ROOT / "frontend" / "src" / "api" / "operation-catalog.ts"
    ).read_text(encoding="utf-8")

    for path in FROZEN_REPORT_PATHS:
        frontend_path = path.removeprefix("/api/v1")
        assert f"path: '{frontend_path}'" in catalog, f"前端 Catalog 缺少 {frontend_path}"


def test_env_example_documents_report_llm_namespace_without_real_secret() -> None:
    """验证报告模块使用独立配置命名空间，并确保示例文件没有真实密钥。"""

    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "REPORT_AI_MODE=llm" in env_example
    assert "REPORT_LLM_PROVIDER=deepseek" in env_example
    assert "REPORT_LLM_BASE_URL=https://api.deepseek.com" in env_example
    assert "REPORT_LLM_MODEL=deepseek-v4-pro" in env_example
    assert "REPORT_LLM_API_KEY=sk-your-report-key" in env_example
    # 只检查真实 DeepSeek 密钥的结构特征，不把任何实际密钥写进测试代码。
    assert re.search(r"sk-[0-9a-f]{32}\b", env_example, flags=re.IGNORECASE) is None
