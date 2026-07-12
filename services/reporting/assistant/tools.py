"""智能报告助手 — 受控报告工具。

本模块实现智能层可以调用的工具函数。每个工具：
1. 接收参数但不接收 LLM 原始 JSON（参数已经过 Python 校验）
2. 执行前再次鉴权
3. 统一返回 AssistantToolResult
4. 复用现有 Registry、Aggregator 和 Orchestrator

Iteration 1 提供三个工具：
- list_report_types：列出当前用户可访问的报告类型
- generate_existing_report：调用现有报告生成流程创建任务
- query_report_status：查询已有报告的状态

工具不直接写库，不重新实现 aggregator/rules。
"""

from __future__ import annotations

import logging
import hashlib
import json
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.reporting.assistant.schemas import AssistantToolResult
from services.reporting.orchestrator import (
    create_report_task_result,
    generate_report_async,
)
from services.reporting.registry import REPORT_REGISTRY, get_report_definition, list_report_types

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具 1：列出报告类型
# ---------------------------------------------------------------------------


def tool_list_report_types(
    *,
    user_role_code: str | None,
) -> AssistantToolResult:
    """列出当前用户可访问的所有报告类型。

    只从 REPORT_REGISTRY 读取；不涉及数据库查询。
    结果可直接用于构建 LLM 可选类型列表。

    Args:
        user_role_code: 当前用户角色。

    Returns:
        AssistantToolResult.data 包含 report_types 列表。
    """
    from services.reporting.assistant.prompts import build_report_catalog

    catalog = build_report_catalog(user_role_code=user_role_code)
    report_types = [
        {
            "report_type": t.report_type,
            "label": t.label,
            "default_period_rule": t.default_period_rule,
            "allowed": t.allowed,
        }
        for t in catalog
    ]
    return AssistantToolResult(
        tool_name="list_report_types",
        status="success",
        data={"report_types": report_types, "total": len(report_types)},
    )


# ---------------------------------------------------------------------------
# 工具 2：生成已有类型的报告
# ---------------------------------------------------------------------------


def tool_generate_existing_report(
    *,
    report_type: str,
    period_start: date,
    period_end: date,
    generated_by: int,
    title: str,
    filters: Optional[dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    db: Session,
) -> AssistantToolResult:
    """调用现有 create_report_task 创建报告任务，不在此处执行生成。

    **重要架构决策（Iteration 1.1）**：
    本函数只创建任务记录并返回。真正的 ``generate_report()`` 由调用方
    （router 层）通过 ``BackgroundTasks.add_task(generate_report_async, report.id)``
    在后台独立 Session 中执行。这保证了：
    1. HTTP 请求线程不阻塞
    2. 与原 POST /api/v1/reports/generate 接口行为一致
    3. 后台任务拥有独立的数据库会话

    幂等处理：
    如果调用方传入了 ``idempotency_key``：
    - 手动请求使用 ``manual:{key}`` 格式
    - create_report_task 内部通过 DB UNIQUE INDEX 保证幂等
    - 幂等命中时返回已有任务，不创建新任务

    Args:
        report_type: 报告类型编码（已经过白名单校验）。
        period_start: 统计周期开始。
        period_end: 统计周期结束。
        generated_by: 当前用户 ID。
        title: 报告标题。
        filters: 筛选条件（可选）。
        idempotency_key: 客户端幂等键（可选），用于防重复提交。
        db: 数据库会话。

    Returns:
        AssistantToolResult，report_id 和任务状态在 data 中。
        调用方根据 data["status"] 决定是否需要注册 BackgroundTasks。
    """
    try:
        definition = get_report_definition(report_type)

        # 使用原子 create_report_task_result，由 orchestrator 在事务内
        # 判断 created（消除调用方 pre-check 的 TOCTOU 竞争）。
        # 三条数据库路径：
        # 1. 提前命中已有幂等键 → created=False
        # 2. INSERT 成功 → created=True
        # 3. IntegrityError → rollback + 查询胜出记录 → created=False
        result = create_report_task_result(
            db,
            report_type=report_type,
            title=title,
            period_start=period_start,
            period_end=period_end,
            generated_by=generated_by,
            request_filters=filters or {},
            idempotency_key=idempotency_key,
            trigger_source="manual",
        )

        # 不在此处同步调用 generate_report()。
        # 调用方（ReportAssistantService → router）负责通过 BackgroundTasks
        # 注册 generate_report_async(result.report.id)，在独立 Session 中执行。
        # 只有原子确认新创建的任务（result.created=True）才需要注册后台任务。

        return AssistantToolResult(
            tool_name="generate_existing_report",
            status="success",
            data={
                "report_id": result.report.id,
                "report_type": report_type,
                "status": result.report.status,
                "created": result.created,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
            report_id=result.report.id,
        )
    except ValueError as exc:
        return AssistantToolResult(
            tool_name="generate_existing_report",
            status="error",
            error=str(exc),
        )
    except Exception as exc:
        logger.exception("报告生成工具调用失败")
        return AssistantToolResult(
            tool_name="generate_existing_report",
            status="error",
            error=f"报告生成失败: {exc.__class__.__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# 工具 3：查询报告状态
# ---------------------------------------------------------------------------


def tool_query_report_status(
    *,
    report_id: int,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """查询已有报告的状态（Iteration 2A：增加权限检查）。

    用于用户追问"刚才那个报告好了吗"时快速查询。

    Args:
        report_id: 报告 ID。
        current_user: 当前用户（用于行级权限检查）。
        db: 数据库会话。

    Returns:
        AssistantToolResult，含状态、时间戳和建议操作。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="query_report_status",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    # 行级权限检查
    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="query_report_status",
            status="error",
            error="无权访问此报告",
        )

    status = report.status
    can_view_detail = status == "completed"
    suggest_retry = status == "failed"

    return AssistantToolResult(
        tool_name="query_report_status",
        status="success",
        data={
            "report_id": report.id,
            "report_type": report.report_type,
            "title": report.report_title,
            "status": status,
            "created_time": report.create_time.isoformat() if report.create_time else None,
            "started_time": report.started_time.isoformat() if report.started_time else None,
            "completed_time": report.completed_time.isoformat() if report.completed_time else None,
            "error_code": report.error_code,
            "error_message": _safe_error_message(report.error_message),
            "can_view_detail": can_view_detail,
            "suggest_retry": suggest_retry,
        },
        report_id=report.id,
        data_quality=report.data_quality,
    )


# ---------------------------------------------------------------------------
# 工具 4：获取报告详情
# ---------------------------------------------------------------------------


def tool_get_report_detail(
    *,
    report_id: int,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """获取已完成报告的结构化详情。

    - 只允许读取 completed 状态的报告
    - 复用现有行级权限
    - 心理报告字段脱敏
    - 不返回 HTML、不将 ORM 对象暴露给 LLM

    Args:
        report_id: 报告 ID。
        current_user: 当前用户。
        db: 数据库会话。

    Returns:
        AssistantToolResult.data 包含结构化 report_content、metric_traces、data_quality。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="get_report_detail",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="get_report_detail",
            status="error",
            error="无权访问此报告",
        )

    if report.status != "completed":
        return AssistantToolResult(
            tool_name="get_report_detail",
            status="error",
            error=f"报告尚未完成，当前状态: {report.status}",
        )

    definition = get_report_definition(report.report_type)
    if current_user and not _can_access_report_type(current_user, definition):
        return AssistantToolResult(
            tool_name="get_report_detail",
            status="error",
            error=f"无权访问报告类型: {report.report_type}",
        )

    content = report.report_content or {}

    # 心理报告字段脱敏
    if report.report_type == "psych_weekly":
        content = _sanitize_psych_content(content)

    # 从报告内容中提取 metric_traces
    metric_traces = content.get("metric_traces", []) if isinstance(content, dict) else []

    return AssistantToolResult(
        tool_name="get_report_detail",
        status="success",
        data={
            "report_id": report.id,
            "report_type": report.report_type,
            "title": report.report_title,
            "schema_version": report.schema_version,
            "period_start": report.period_start.isoformat() if report.period_start else None,
            "period_end": report.period_end.isoformat() if report.period_end else None,
            "content": content,
            "metric_traces": metric_traces,
        },
        report_id=report.id,
        data_quality=report.data_quality,
    )


# ---------------------------------------------------------------------------
# 工具 5：申请风险明细钻取
# ---------------------------------------------------------------------------


def tool_get_application_risk_items(
    *,
    report_id: int,
    limit: int = 5,
    risk_level: Optional[str] = None,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """从已完成报告中提取申请风险明细，按 risk_score 降序排列。

    排序由 Python 完成，不依赖 LLM。

    Args:
        report_id: 报告 ID（必须是 application_risk 类型）。
        limit: 返回数量上限（强制 ≤ 10）。
        risk_level: 可选过滤（high/medium/low）。
        current_user: 当前用户。
        db: 数据库会话。

    Returns:
        AssistantToolResult.data 包含 items 和 referenced_entities 列表。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="get_application_risk_items",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="get_application_risk_items",
            status="error",
            error="无权访问此报告",
        )

    if report.report_type != "application_risk":
        return AssistantToolResult(
            tool_name="get_application_risk_items",
            status="error",
            error=f"报告类型为 {report.report_type}，不支持风险明细钻取",
        )

    if report.status != "completed":
        return AssistantToolResult(
            tool_name="get_application_risk_items",
            status="error",
            error=f"报告尚未完成（{report.status}），无法读取风险明细",
        )

    content = report.report_content or {}
    risk_items = content.get("risk_items", []) if isinstance(content, dict) else []

    # 按 risk_score 降序排列（Python 确定性排序）
    risk_items_sorted = sorted(risk_items, key=lambda x: x.get("risk_score", 0), reverse=True)

    # 按 risk_level 过滤
    if risk_level:
        risk_items_sorted = [r for r in risk_items_sorted if r.get("risk_level") == risk_level]

    # 强制上限
    safe_limit = min(max(1, limit), 10)
    top_items = risk_items_sorted[:safe_limit]

    # 构建 ReferencedEntity 列表
    from services.reporting.assistant.schemas import ReferencedEntity
    entities: list[dict[str, Any]] = []
    for i, item in enumerate(top_items):
        entities.append(ReferencedEntity(
            position=i + 1,
            entity_type="application",
            entity_id=str(item.get("application_id", "")),
            display_name=f"申请 #{item.get('application_id')}",
            source_report_id=report_id,
            metadata={
                "risk_score": item.get("risk_score", 0),
                "risk_level": item.get("risk_level", ""),
            },
        ).model_dump())

    return AssistantToolResult(
        tool_name="get_application_risk_items",
        status="success",
        data={
            "report_id": report_id,
            "total_items": len(risk_items_sorted),
            "returned_items": len(top_items),
            "items": top_items,
            "referenced_entities": entities,
        },
        report_id=report_id,
        data_quality=report.data_quality,
    )


# ---------------------------------------------------------------------------
# 工具 6：申请风险详情
# ---------------------------------------------------------------------------


def tool_get_application_risk_detail(
    *,
    report_id: int,
    application_id: str,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """获取单个申请的完整风险详情。

    返回内容必须来自报告，不得补充报告内容中不存在的原因。

    Args:
        report_id: 报告 ID。
        application_id: 申请 ID。
        current_user: 当前用户。
        db: 数据库会话。

    Returns:
        AssistantToolResult.data 包含风险分、等级、原因、缺失材料、MetricTrace。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="get_application_risk_detail",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="get_application_risk_detail",
            status="error",
            error="无权访问此报告",
        )

    if report.status != "completed":
        return AssistantToolResult(
            tool_name="get_application_risk_detail",
            status="error",
            error=f"报告尚未完成，无法读取风险详情",
        )

    content = report.report_content or {}
    risk_items = content.get("risk_items", []) if isinstance(content, dict) else []

    # 查找目标申请
    target = None
    for item in risk_items:
        if str(item.get("application_id", "")) == str(application_id):
            target = item
            break

    if not target:
        return AssistantToolResult(
            tool_name="get_application_risk_detail",
            status="error",
            error=f"报告中未找到申请: {application_id}",
        )

    # 提取 MetricTrace
    metric_traces = content.get("metric_traces", []) if isinstance(content, dict) else []

    return AssistantToolResult(
        tool_name="get_application_risk_detail",
        status="success",
        data={
            "report_id": report_id,
            "application_id": application_id,
            "risk_score": target.get("risk_score"),
            "risk_level": target.get("risk_level"),
            "risk_reasons": target.get("risk_reasons", []),
            "missing_materials": target.get("missing_materials", []),
            "next_action": target.get("next_action"),
            "stage": target.get("stage"),
            "student_id": target.get("student_id"),
            "owner_id": target.get("owner_id"),
            "metric_traces": metric_traces,
        },
        report_id=report_id,
        data_quality=report.data_quality,
    )


# ---------------------------------------------------------------------------
# 工具 7：MetricTrace 指标追溯
# ---------------------------------------------------------------------------

# 受控指标别名映射 — 只允许这些白名单内的指标名
_METRIC_ALIASES: dict[str, str] = {
    "风险分": "risk_score",
    "高风险数量": "high_risk_count",
    "逾期数量": "overdue_count",
    "缺失材料数": "missing_material_count",
    "ROI": "roi",
    "CPL": "cpl",
    "CAC": "cac",
    "SLA超时数": "sla_timeout_count",
    "SLA 超时数": "sla_timeout_count",
    "转化率": "conversion_rate",
}


def tool_get_metric_trace(
    *,
    report_id: int,
    metric_name: str,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """查询指定指标的追溯信息（来源表、公式、过滤条件）。

    指标名必须经过受控别名映射，不允许 LLM 传递任意 JSONPath 或 SQL 字段名。

    Args:
        report_id: 报告 ID。
        metric_name: 指标名称（白名单内的中文名或编码名）。
        current_user: 当前用户。
        db: 数据库会话。

    Returns:
        AssistantToolResult.data 包含 source_tables、formula、filters、period。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="get_metric_trace",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="get_metric_trace",
            status="error",
            error="无权访问此报告",
        )

    # 解析指标名称（先查别名，再直接匹配）
    resolved_name = _METRIC_ALIASES.get(metric_name, metric_name)

    # 从报告内容中查找 MetricTrace
    content = report.report_content or {}
    traces = content.get("metric_traces", []) if isinstance(content, dict) else []

    matched = None
    for trace in traces:
        if trace.get("metric_name") == resolved_name:
            matched = trace
            break

    if not matched:
        # 尝试模糊匹配
        for trace in traces:
            if resolved_name.lower() in trace.get("metric_name", "").lower():
                matched = trace
                break

    if not matched:
        return AssistantToolResult(
            tool_name="get_metric_trace",
            status="error",
            error=f"未知指标: {metric_name}。可用指标: {[t.get('metric_name') for t in traces]}",
        )

    return AssistantToolResult(
        tool_name="get_metric_trace",
        status="success",
        data={
            "metric_name": matched.get("metric_name"),
            "source_tables": matched.get("source_tables", []),
            "formula": matched.get("formula"),
            "filters": matched.get("filters", {}),
            "period_start": report.period_start.isoformat() if report.period_start else None,
            "period_end": report.period_end.isoformat() if report.period_end else None,
        },
        report_id=report_id,
        data_quality=report.data_quality,
    )


# ---------------------------------------------------------------------------
# 工具 8：查询数据质量
# ---------------------------------------------------------------------------


def tool_get_report_data_quality(
    *,
    report_id: int,
    current_user: Any = None,
    db: Session,
) -> AssistantToolResult:
    """返回报告的数据质量详情，含对回答的限制说明。

    DataQuality 对回答的约束：
    - ok → 可以正常分析
    - warning → 必须说明限制
    - empty → 不得解释趋势
    - degraded → 不得给出强结论
    - failed → 不得生成业务分析

    Args:
        report_id: 报告 ID。
        current_user: 当前用户。
        db: 数据库会话。

    Returns:
        AssistantToolResult.data 包含 quality 详情和回答限制。
    """
    from models.report import ReportGeneration

    report = db.query(ReportGeneration).filter_by(id=report_id).first()
    if not report:
        return AssistantToolResult(
            tool_name="get_report_data_quality",
            status="error",
            error=f"报告不存在: {report_id}",
        )

    if current_user and not _can_access_report(report, current_user):
        return AssistantToolResult(
            tool_name="get_report_data_quality",
            status="error",
            error="无权访问此报告",
        )

    dq = report.data_quality or {}
    level = dq.get("level", "ok") if isinstance(dq, dict) else "ok"

    # 根据 quality level 确定回答限制
    limitations = _data_quality_limitations(level)

    return AssistantToolResult(
        tool_name="get_report_data_quality",
        status="success",
        data={
            "report_id": report_id,
            "level": level,
            "level_description": _DATA_QUALITY_DESCRIPTIONS.get(level, "未知"),
            "warnings": dq.get("warnings", []) if isinstance(dq, dict) else [],
            "data_source": dq.get("data_source", "unknown") if isinstance(dq, dict) else "unknown",
            "limitations": limitations,
        },
        report_id=report_id,
        data_quality=dq if isinstance(dq, dict) else None,
    )


# ============================================================================
# 内部辅助函数
# ============================================================================


_DATA_QUALITY_DESCRIPTIONS: dict[str, str] = {
    "ok": "数据源完整，可以基于当前报告进行分析",
    "warning": "部分可选数据源缺失，以下结论仅基于现有数据",
    "empty": "当前统计周期没有有效数据，无法判断趋势",
    "degraded": "报告处于降级状态，只能给出有限结论",
    "failed": "报告生成失败，不能基于该报告进行业务判断",
}


def _data_quality_limitations(level: str) -> list[str]:
    """根据数据质量等级返回对回答的限制。"""
    if level == "ok":
        return []
    if level == "warning":
        return ["说明数据局限性"]
    if level == "empty":
        return ["不得解释趋势", "不得分析变化原因"]
    if level == "degraded":
        return ["不得给出强结论", "必须说明降级原因"]
    if level == "failed":
        return ["不得生成业务分析", "不得做任何趋势判断"]
    return ["未知数据质量，需谨慎"]


def _can_access_report(report, current_user: Any) -> bool:
    """行级权限检查：复用现有报告访问规则。"""
    if current_user.role_code in ("admin", "manager", "team_leader"):
        return True
    return report.generated_by == getattr(current_user, "id", None)


def _can_access_report_type(current_user: Any, definition: Any) -> bool:
    """报告类型角色白名单检查。"""
    if current_user.role_code == "admin":
        return True
    return current_user.role_code in (definition.allowed_roles or set())


def _safe_error_message(raw: Optional[str]) -> Optional[str]:
    """截断错误信息，避免泄露内部细节。"""
    if not raw:
        return None
    return raw[:200]


def _sanitize_psych_content(content: dict[str, Any]) -> dict[str, Any]:
    """心理报告字段脱敏：移除敏感个人标识。"""
    if not isinstance(content, dict):
        return content
    safe = dict(content)
    # 移除可能包含敏感信息的字段
    for key in list(safe.keys()):
        if key in ("alert_status", "emotion_trend"):
            items = safe.get(key, [])
            if isinstance(items, list):
                safe[key] = [
                    {k: v for k, v in (item.items() if isinstance(item, dict) else {})
                     if k not in ("student_name", "student_id")}
                    for item in items
                ]
    return safe
def tool_compare_report_metrics(*, report_type: str, comparison_period: Any,
                                metric_names: list[str], current_user: Any,
                                db: Session) -> AssistantToolResult:
    """只读比较两个精确周期的受控指标，并生成稳定、不可交换的证据。"""
    from models.report import ReportGeneration
    from services.reporting.aggregators import aggregate_report
    from services.reporting.assistant.comparison import calculate_values, evaluate_comparison_quality
    from services.reporting.assistant.guardrails import validate_comparison_access
    from services.reporting.assistant.metric_catalog import get_metric_definition
    from services.reporting.assistant.metric_resolvers import extract_metric_values
    from services.reporting.assistant.schemas import EvidenceItem, MetricComparison

    report_definition = get_report_definition(report_type)
    if not metric_names:
        raise ValueError("metric_names 不能为空")
    definitions = [get_metric_definition(report_type, name) for name in metric_names]
    validate_comparison_access(current_user, report_definition, definitions)

    def load(start: date, end: date) -> dict[str, Any]:
        report = (db.query(ReportGeneration).filter_by(
            report_type=report_type, period_start=start, period_end=end, status="completed"
        ).order_by(ReportGeneration.update_time.desc(), ReportGeneration.create_time.desc(),
                   ReportGeneration.id.desc()).first())
        if report:
            if not _can_access_report(report, current_user):
                raise PermissionError("无权访问对比报告")
            return {"content": report.report_content or {}, "quality": report.data_quality or {},
                    "id": report.id, "schema": report.schema_version}
        aggregated = aggregate_report(db, report_type, start, end, {})
        quality = aggregated.data_quality.model_dump()
        return {"content": aggregated.content, "quality": quality, "id": 0,
                "schema": report_definition.schema_version}

    current = load(comparison_period.current_start, comparison_period.current_end)
    previous = load(comparison_period.previous_start, comparison_period.previous_end)
    metric_signature = hashlib.sha256("|".join(
        f"{item.report_type}:{item.metric_name}:{item.resolver_name}:{item.value_path}:"
        f"{item.value_type}:{item.dimension_name}" for item in definitions
    ).encode()).hexdigest()
    current_signature = current["content"].get("_metric_definition_signature", metric_signature)
    previous_signature = previous["content"].get("_metric_definition_signature", metric_signature)
    current_days = (comparison_period.current_end - comparison_period.current_start).days
    previous_days = (comparison_period.previous_end - comparison_period.previous_start).days
    compatible = (
        current["schema"] == previous["schema"] == report_definition.schema_version
        and current_signature == previous_signature == metric_signature
        and current_days == previous_days
        and comparison_period.previous_end < comparison_period.current_start
    )
    gate = evaluate_comparison_quality(current["quality"], previous["quality"], compatible=compatible)
    comparisons: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for definition in definitions:
        def exact_map(content: dict[str, Any]) -> dict[tuple[tuple[str, str], ...], Any]:
            """按完整维度键对齐；重复维度会拒绝，避免后一个值静默覆盖前一个值。"""
            result = {}
            for extracted in extract_metric_values(definition, content):
                key = tuple(sorted(extracted.dimension.items()))
                if key in result:
                    raise ValueError(f"指标 {definition.metric_name} 存在重复维度: {dict(key)}")
                result[key] = extracted
            return result
        current_map = exact_map(current["content"])
        previous_map = exact_map(previous["content"])
        for key in sorted(set(current_map) | set(previous_map)):
            dimension = dict(key)
            current_value = current_map[key].value if key in current_map else None
            previous_value = previous_map[key].value if key in previous_map else None
            values = gate.apply(calculate_values(current_value, previous_value, value_type=definition.value_type))
            def evidence_id(role: str) -> str:
                canonical = json.dumps(dimension, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                digest = hashlib.sha256(
                    f"{report_type}|{definition.metric_name}|{canonical}|{role}".encode()
                ).digest()
                return f"E{int.from_bytes(digest[:10], 'big')}"
            ids = {role: evidence_id(role) for role in ("current", "previous", "delta", "change_rate")}
            comparisons.append(MetricComparison(
                report_type=report_type, metric_name=definition.metric_name, label=definition.label,
                dimension=dimension, current_value=current_value, previous_value=previous_value,
                delta=values.delta, change_rate=values.change_rate, direction=values.direction,
                unit=definition.unit, current_evidence_id=ids["current"],
                previous_evidence_id=ids["previous"],
            ).model_dump())
            for role, value, label, source_id in (
                ("current", current_value, comparison_period.current_label, current["id"]),
                ("previous", previous_value, comparison_period.previous_label, previous["id"]),
                ("delta", values.delta, f"{comparison_period.current_label}-{comparison_period.previous_label}", 0),
                ("change_rate", values.change_rate, f"{comparison_period.current_label}/{comparison_period.previous_label}", 0),
            ):
                formula = "current - previous" if role == "delta" else "(current - previous) / abs(previous)" if role == "change_rate" else None
                evidence.append(EvidenceItem(
                    evidence_id=ids[role], metric_name=definition.metric_name,
                    label=f"{definition.label}-{role}", value=value, unit=definition.unit,
                    source_report_id=source_id, source_tables=[path[0] for path in definition.source_fields],
                    formula=formula, report_type=report_type, period_label=label,
                    comparison_role=role, dimension=dimension, source="compare_report_metrics",
                    reference=".".join(definition.value_path or (definition.resolver_name or "",)),
                ).model_dump())
    return AssistantToolResult(tool_name="compare_report_metrics", status="success", data={
        "comparison": comparisons, "evidence": evidence,
        "current_data_quality": current["quality"], "previous_data_quality": previous["quality"],
        "periods": comparison_period.model_dump(), "assumptions": list(comparison_period.assumptions),
    })
