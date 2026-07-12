"""智能报告助手 — FastAPI 路由。

本路由提供智能报告助手的 HTTP 接口。路由自身不写业务逻辑，
所有处理委托给 ``ReportAssistantService.handle_message()``。

接口：
    POST /api/v1/reports/assistant/messages — 自然语言生成/查询报告

权限：
    学生角色被拦截（ensure_management_user）；具体报告类型权限在 Service 层
    通过 build_report_catalog() 按角色过滤。

架构位置：
    POST /api/v1/reports/assistant/messages
    → routers/report_assistant.py（本文件）
    → ReportAssistantService.handle_message()
    → 受控 Python Tools
    → 现有 Registry → Aggregator → Rules → Orchestrator
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from schemas.report import (  # 复用现有 API Schema 中的 ReportTaskResponse 等
    ReportDetailResponse,
)
from services.reporting.assistant.config import settings
from services.reporting.assistant.schemas import (
    ReportAssistantMessageRequest,
    ReportAssistantMessageResponse,
)
from services.reporting.assistant.service import ReportAssistantService
from utils.auth import CurrentUser, ensure_management_user, get_current_user
from utils.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /messages — 自然语言对话入口
# ---------------------------------------------------------------------------


@router.post(
    "/messages",
    response_model=ReportAssistantMessageResponse,
)
def handle_assistant_message(
    request: ReportAssistantMessageRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportAssistantMessageResponse:
    """智能报告助手 — 自然语言对话入口。

    接收用户自然语言输入，自动识别报告类型、解析时间范围、
    判断权限和置信度，然后通过 BackgroundTasks 异步调用现有报告生成流程。

    请求示例::

        {
          "message": "帮我看看现在申请风险，有没有特别危险的",
          "conversation_context": {
            "conversation_id": "6a0975be-..."
          },
          "client_request_id": "optional-idempotency-key"
        }

    HTTP 状态码约定：
    - 创建新任务 → 202 Accepted + status="generating"
    - 幂等命中已完成 → 200 OK + status="completed"
    - 需要澄清 → 200 OK + status="needs_clarification"
    - 权限拒绝 → 403 Forbidden
    - 错误 → 200 OK + status="error"

    Args:
        request: 用户消息 + 会话上下文。
        response: FastAPI Response 对象，用于动态设置 HTTP 状态码。
        background_tasks: FastAPI 后台任务管理器（依赖注入）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入，来自 JWT）。

    Returns:
        ReportAssistantMessageResponse，包含意图、回答、报告 ID 和更新后的上下文。

    Raises:
        403: 学生角色禁止使用管理报告功能。
        503: REPORT_ASSISTANT_ENABLED=false 时功能未开启。
    """
    # 功能开关：REPORT_ASSISTANT_ENABLED=false 时返回稳定错误
    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能报告助手功能未开启。设置 REPORT_ASSISTANT_ENABLED=true 以启用。",
        )

    # 权限检查：学生角色禁止访问管理报告
    ensure_management_user(current_user)

    service = ReportAssistantService()
    result = service.handle_message(
        request=request,
        current_user=current_user,
        db=db,
        background_tasks=background_tasks,
    )

    # 根据处理状态动态设置 HTTP 状态码
    # 遵循与原 POST /api/v1/reports/generate 接口一致的异步契约
    if result.status == "generating":
        response.status_code = status.HTTP_202_ACCEPTED
    elif result.status == "permission_denied":
        response.status_code = status.HTTP_403_FORBIDDEN
    elif result.status == "not_found":
        response.status_code = status.HTTP_404_NOT_FOUND
    elif result.status == "error":
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        response.status_code = status.HTTP_200_OK

    logger.info(
        "智能报告助手对话完成: user=%s intent=%s report_type=%s confidence=%.2f status=%s http_status=%d",
        current_user.username,
        result.intent.value,
        result.report_type or "-",
        result.confidence,
        result.status,
        response.status_code,
    )

    return result
