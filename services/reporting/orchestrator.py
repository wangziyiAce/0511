"""智能报告 V2 编排层。

编排层是报告模块的“交通枢纽”：

1. 接收手动接口、重试接口、定时调度器的生成请求；
2. 创建 report_generation 任务记录；
3. 调用聚合器计算业务数字；
4. 调用 AI 解释层补充说明；
5. 使用后端模板渲染 HTML；
6. 保存成功或失败状态。

你可以把它理解成 FastAPI 后端里的一个小型任务流引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.report import ReportGeneration
from services.reporting.aggregators import aggregate_report
from services.reporting.ai_generator import enrich_content_with_ai
from services.reporting.registry import get_report_definition
from services.reporting.renderer import render_report_html
from services.reporting.schemas import REPORT_SCHEMA_VERSION, DataQuality
from utils.database import SessionLocal


def resolve_period(
    period_start: Optional[date],
    period_end: Optional[date],
    *,
    period_rule: str = "previous_week",
) -> tuple[date, date]:
    """解析统计周期。

    手动请求优先使用传入日期；定时任务可用 period_rule 自动推导。
    """

    if period_start and period_end:
        return period_start, period_end
    today = date.today()
    if period_rule == "previous_day":
        target = today - timedelta(days=1)
        return target, target
    if period_rule == "previous_month":
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        return first_prev_month, last_prev_month
    # 默认 previous_week：统计上一个自然周（周一到周日）。
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return last_monday, last_sunday


def build_idempotency_key(
    *,
    report_type: str,
    period_start: date,
    period_end: date,
    schedule_id: Optional[int] = None,
    request_key: Optional[str] = None,
) -> Optional[str]:
    """生成幂等键。

    手动接口优先使用 ``Idempotency-Key`` 请求头；
    定时任务使用 ``schedule:{id}:{start}:{end}``。
    """

    if request_key:
        return f"manual:{request_key}"
    if schedule_id:
        return f"schedule:{schedule_id}:{period_start.isoformat()}:{period_end.isoformat()}"
    return None


# ---------------------------------------------------------------------------
# 原子任务创建结果 — Iteration 1.3
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportTaskCreationResult:
    """``create_report_task_result()`` 的返回类型。

    与普通 ``ReportGeneration`` 返回值不同，此类型明确区分"当前请求
    是否真正完成了新记录的 INSERT"，消除调用方自己 pre-check 的 TOCTOU 竞争。

    Attributes:
        report: 报告任务记录（新创建或已有）。
        created: True 表示当前事务真正完成了 INSERT；False 表示命中已有记录。
    """

    report: ReportGeneration
    created: bool


def create_report_task_result(
    db: Session,
    *,
    report_type: str,
    title: str,
    period_start: Optional[date],
    period_end: Optional[date],
    generated_by: Optional[int],
    request_filters: Optional[dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    trigger_source: str = "manual",
    schedule_id: Optional[int] = None,
    retry_of_report_id: Optional[int] = None,
    retry_count: int = 0,
) -> ReportTaskCreationResult:
    """创建报告任务记录，并原子返回是否真正由当前请求创建。

    与 ``create_report_task()`` 功能相同，但返回 ``ReportTaskCreationResult``
    而非裸 ``ReportGeneration``，使调用方能可靠判断是否需要注册后台任务。

    三条数据库路径：
    1. 提前命中已有记录 → created=False
    2. 当前事务 INSERT 成功 → created=True
    3. 并发 UNIQUE 冲突 → rollback + 查询胜出记录 → created=False

    原 ``create_report_task()`` 保持向后兼容：
        create_report_task(...) → create_report_task_result(...).report
    """

    definition = get_report_definition(report_type)
    start, end = resolve_period(period_start, period_end, period_rule=definition.default_period_rule)
    final_key = build_idempotency_key(
        report_type=report_type,
        period_start=start,
        period_end=end,
        schedule_id=schedule_id,
        request_key=idempotency_key,
    )

    # ---- 路径 1：提前命中已有幂等键 ----
    if final_key:
        existing = db.query(ReportGeneration).filter_by(idempotency_key=final_key).first()
        if existing:
            return ReportTaskCreationResult(report=existing, created=False)

    report = ReportGeneration(
        report_type=report_type,
        report_title=title,
        period_start=start,
        period_end=end,
        status="pending",
        schema_version=REPORT_SCHEMA_VERSION,
        generated_by=generated_by,
        schedule_id=schedule_id,
        retry_of_report_id=retry_of_report_id,
        trigger_source=trigger_source,
        retry_count=retry_count,
        idempotency_key=final_key,
        request_filters=request_filters or {},
        data_quality=DataQuality().model_dump(),
    )
    db.add(report)

    try:
        db.commit()
        db.refresh(report)
        # ---- 路径 2：INSERT 成功 ----
        return ReportTaskCreationResult(report=report, created=True)
    except IntegrityError:
        # ---- 路径 3：并发 UNIQUE 冲突 ----
        db.rollback()
        if final_key:
            winner = db.query(ReportGeneration).filter_by(idempotency_key=final_key).first()
            if winner:
                return ReportTaskCreationResult(report=winner, created=False)
        # 极端情况：无法恢复，重新抛出
        raise


def create_report_task(
    db: Session,
    *,
    report_type: str,
    title: str,
    period_start: Optional[date],
    period_end: Optional[date],
    generated_by: Optional[int],
    request_filters: Optional[dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    trigger_source: str = "manual",
    schedule_id: Optional[int] = None,
    retry_of_report_id: Optional[int] = None,
    retry_count: int = 0,
) -> ReportGeneration:
    """创建报告任务记录。

    注意：这里只创建任务，不等待 LLM 调用，也不在请求线程里做重计算。
    FastAPI 接口会返回 202，后台任务再调用 ``generate_report_async``。

    自 Iteration 1.3 起委托给 ``create_report_task_result()``，
    保持向后兼容的返回类型。
    """
    return create_report_task_result(
        db,
        report_type=report_type,
        title=title,
        period_start=period_start,
        period_end=period_end,
        generated_by=generated_by,
        request_filters=request_filters,
        idempotency_key=idempotency_key,
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        retry_of_report_id=retry_of_report_id,
        retry_count=retry_count,
    ).report


def _mark_failed(db: Session, report: ReportGeneration, error_code: str, error: Exception) -> None:
    report.status = "failed"
    report.error_code = error_code
    report.error_message = f"{error.__class__.__name__}: {error}"[:1000]
    report.completed_time = datetime.now()
    db.commit()


def generate_report(report_id: int, db: Session) -> ReportGeneration:
    """同步执行一次报告生成。

    后台任务、定时调度器、测试都可以调用它。它接收一个已经创建好的
    ``report_generation`` 记录，然后把状态推进到 completed 或 failed。

    **原子领取（Iteration 1.3）**：使用条件 UPDATE 将 pending 原子切换为
    generating。如果 updated_rows != 1，说明任务已被其他 worker 领取或状态
    已不是 pending，直接返回不重复执行。
    """

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        raise ValueError(f"报告不存在: {report_id}")

    # ---- 原子领取：只有 pending 状态的任务才允许进入 generating ----
    # 条件 UPDATE 防止两个并发 worker 同时读到 pending 后都尝试生成。
    now = datetime.now()
    updated_rows = (
        db.query(ReportGeneration)
        .filter(
            ReportGeneration.id == report_id,
            ReportGeneration.status == "pending",
        )
        .update(
            {
                ReportGeneration.status: "generating",
                ReportGeneration.started_time: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()

    if updated_rows != 1:
        # 任务已被其他 worker 领取，或状态已不是 pending
        db.refresh(report)
        return report

    # 刷新以获取 UPDATE 后的状态
    db.refresh(report)

    try:

        definition = get_report_definition(report.report_type)
        period = {
            "start": report.period_start.isoformat() if report.period_start else None,
            "end": report.period_end.isoformat() if report.period_end else None,
        }
        aggregated = aggregate_report(
            db=db,
            report_type=report.report_type,
            period_start=report.period_start,
            period_end=report.period_end,
            filters=report.request_filters or {},
        )
        content = enrich_content_with_ai(
            definition=definition,
            title=report.report_title,
            period=period,
            content=aggregated.content,
            data_quality=aggregated.data_quality,
        )
        # 再次用独立 Schema 校验，保证 LLM 或本地解释不会破坏结构。
        validated = definition.content_model.model_validate(content)
        content_dict = validated.model_dump(mode="json")

        report.report_content = content_dict
        report.aggregated_data_snapshot = aggregated.snapshot
        report.data_quality = aggregated.data_quality.model_dump()
        report.report_html = render_report_html(
            definition=definition,
            title=report.report_title,
            period=period,
            content=content_dict,
            data_quality=report.data_quality,
        )
        report.status = "completed"
        report.completed_time = datetime.now()
        report.error_code = None
        report.error_message = None
        db.commit()
        db.refresh(report)
        return report
    except Exception as exc:
        _mark_failed(db, report, "REPORT_GENERATION_FAILED", exc)
        db.refresh(report)
        return report


def generate_report_async(report_id: int) -> None:
    """FastAPI BackgroundTasks 使用的入口。

    异步任务必须自己创建数据库 Session，不能复用请求里的 Session。
    """

    db = SessionLocal()
    try:
        generate_report(report_id, db)
    finally:
        db.close()


def retry_report(db: Session, *, report_id: int, generated_by: Optional[int]) -> ReportGeneration:
    """创建新的重试记录，不覆盖原失败记录。"""

    original = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not original:
        raise ValueError(f"报告不存在: {report_id}")
    return create_report_task(
        db,
        report_type=original.report_type,
        title=f"{original.report_title}（重试）",
        period_start=original.period_start,
        period_end=original.period_end,
        generated_by=generated_by,
        request_filters=original.request_filters or {},
        trigger_source="retry",
        retry_of_report_id=original.id,
        retry_count=(original.retry_count or 0) + 1,
    )

