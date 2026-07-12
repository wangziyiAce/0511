"""智能报告模块 V2 路由。

接口设计重点：

* ``POST /generate`` 返回 202：只创建任务，不等待 Dify；
* ``GET /types`` 暴露 10 类报告的 Schema、权限和过滤条件；
* ``POST /{id}/retry`` 创建新的重试记录，不覆盖原失败记录；
* ``/actions`` 把报告建议转成可跟踪的管理行动项。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from models.report import ReportAction, ReportGeneration
from schemas.report import (
    ReportActionCreate,
    ReportActionResponse,
    ReportActionUpdate,
    ReportDetailResponse,
    ReportGenerateRequest,
    ReportListResponse,
    ReportTaskResponse,
    ReportTypeResponse,
)
from services.reporting.orchestrator import create_report_task, generate_report_async, retry_report
from services.reporting.registry import get_report_definition, list_report_types
from utils.auth import CurrentUser, ensure_report_permission, get_current_user
from utils.database import get_db


router = APIRouter()


def _get_definition_or_400(report_type: str):
    try:
        return get_report_definition(report_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _check_report_row_access(report: ReportGeneration, user: CurrentUser) -> None:
    """报告记录级访问控制。

    当前项目没有完整组织树和客户归属表，所以这里实现最小可讲清楚版本：
    admin/manager/team_leader 可查看管理范围报告；普通员工只能查看自己生成的报告。
    """

    if user.role_code in {"admin", "manager", "team_leader"}:
        return
    if report.generated_by != user.id:
        raise HTTPException(status_code=403, detail="只能访问自己生成的报告")


@router.get("/types", response_model=list[ReportTypeResponse])
def get_report_types(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ReportTypeResponse]:
    """返回报告类型、Schema 版本、权限和可用过滤条件。"""

    if current_user.role_code == "student" or current_user.user_type == "student":
        raise HTTPException(status_code=403, detail="学生角色禁止访问管理报告类型")
    result: list[ReportTypeResponse] = []
    for definition in list_report_types():
        result.append(
            ReportTypeResponse(
                report_type=definition.report_type,
                label=definition.label,
                schema_version=definition.schema_version,
                allowed_roles=list(definition.allowed_roles),
                template_name=definition.template_name,
                default_period_rule=definition.default_period_rule,
                available_filters=list(definition.available_filters),
                json_schema=definition.content_model.model_json_schema(),
            )
        )
    return result


@router.post(
    "/generate",
    response_model=ReportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_report_endpoint(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportGeneration:
    """创建报告生成任务。

    数字聚合和 Dify 调用在后台执行；接口快速返回任务 ID。
    """

    definition = _get_definition_or_400(request.report_type)
    ensure_report_permission(current_user, definition.allowed_roles)
    report = create_report_task(
        db,
        report_type=request.report_type,
        title=request.report_title,
        period_start=request.period_start,
        period_end=request.period_end,
        generated_by=current_user.id,
        request_filters=request.filters,
        idempotency_key=idempotency_key,
        trigger_source="manual",
    )
    if report.status in {"pending", "failed"}:
        background_tasks.add_task(generate_report_async, report.id)
    return report


@router.get("", response_model=ReportListResponse)
def list_reports(
    report_type: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportListResponse:
    """分页查询报告列表。"""

    if current_user.role_code == "student" or current_user.user_type == "student":
        raise HTTPException(status_code=403, detail="学生角色禁止访问管理报告")

    query = db.query(ReportGeneration)
    if report_type:
        query = query.filter(ReportGeneration.report_type == report_type)
    if status_filter:
        query = query.filter(ReportGeneration.status == status_filter)
    if start_date:
        query = query.filter(ReportGeneration.period_start >= start_date)
    if end_date:
        query = query.filter(ReportGeneration.period_end <= end_date)
    if current_user.role_code not in {"admin", "manager", "team_leader"}:
        query = query.filter(ReportGeneration.generated_by == current_user.id)

    total = query.count()
    rows = (
        query.order_by(ReportGeneration.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReportListResponse(
        items=[ReportTaskResponse.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{report_id}", response_model=ReportDetailResponse)
def get_report_detail(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportGeneration:
    """查询报告详情。"""

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    _check_report_row_access(report, current_user)
    return report


@router.post(
    "/{report_id}/retry",
    response_model=ReportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_report_endpoint(
    report_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportGeneration:
    """创建新的重试记录，不覆盖原报告。"""

    original = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="报告不存在")
    _check_report_row_access(original, current_user)
    definition = _get_definition_or_400(original.report_type)
    ensure_report_permission(current_user, definition.allowed_roles)

    new_report = retry_report(db, report_id=report_id, generated_by=current_user.id)
    background_tasks.add_task(generate_report_async, new_report.id)
    return new_report


@router.post("/{report_id}/actions", response_model=ReportActionResponse)
def create_report_action(
    report_id: int,
    request: ReportActionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportAction:
    """把报告建议转成行动项。

    请求来自报告详情页，``report_id`` 决定行动项归属；当前用户必须能访问该报告。
    AI 建议不会自动成为任务，必须由管理者/员工确认后才写入 ``report_action``。
    成功返回带数据库 ID 和状态的行动项；报告不存在返回 404，越权返回 403。
    """

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    _check_report_row_access(report, current_user)

    action = ReportAction(
        report_id=report_id,
        suggestion_text=request.suggestion_text,
        risk_code=request.risk_code,
        owner_id=request.owner_id or current_user.id,
        due_time=request.due_time,
        target_value=request.target_value,
        status="confirmed",
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action

@router.get("/{report_id}/actions", response_model=list[ReportActionResponse])
def list_report_actions(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ReportAction]:
    """查询指定报告的行动项，供报告详情页展示闭环进度。

    当前用户必须先通过报告行级权限校验；报告不存在返回 404，越权返回 403。
    本接口只读数据库，不修改行动状态；没有行动项时返回空列表。
    """

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    _check_report_row_access(report, current_user)
    return db.query(ReportAction).filter_by(report_id=report_id).order_by(ReportAction.create_time.desc()).all()


@router.patch("/actions/{action_id}", response_model=ReportActionResponse)
def update_report_action(
    action_id: int,
    request: ReportActionUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportAction:
    """更新已有行动项的状态、负责人或完成数据。

    请求来自报告行动管理界面，只更新前端实际提交的字段。行动项及其关联报告都
    必须存在，并通过关联报告执行行级鉴权；任一关联缺失时返回 404，避免跳过鉴权
    后继续写库。成功后提交事务并返回数据库刷新后的行动项。
    """

    action = db.query(ReportAction).filter_by(id=action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="行动项不存在")
    report = db.query(ReportGeneration).filter_by(id=action.report_id).first()
    # 行动项的权限继承自报告；关联报告缺失时必须拒绝，不能 fail-open。
    if not report:
        raise HTTPException(status_code=404, detail="行动项关联的报告不存在")
    _check_report_row_access(report, current_user)
    # 仅取前端实际传入字段，避免部分更新覆盖未提交的数据。
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(action, field, value)
    # 将本次状态变化提交到数据库，并读回更新时间等数据库生成字段。
    db.commit()
    db.refresh(action)
    return action
