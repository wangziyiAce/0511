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

from datetime import date, datetime, timedelta
from typing import Any, Optional

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
    if final_key:
        existing = db.query(ReportGeneration).filter_by(idempotency_key=final_key).first()
        if existing:
            return existing

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
    db.commit()
    db.refresh(report)
    return report


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
    """

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        raise ValueError(f"报告不存在: {report_id}")

    try:
        report.status = "generating"
        report.started_time = datetime.now()
        db.commit()

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

