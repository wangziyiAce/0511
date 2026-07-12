"""智能报告助手 — 总编排服务。

本模块是智能交互层的核心编排器。它把意图识别、时间解析、澄清判断和
工具调用串联成一个完整的请求处理流程。

处理流程：
    用户输入
    → 获取允许的报告类型（从 Registry 按角色过滤）
    → Intent Parser（LLM Structured Output 或关键词降级）
    → Clarification Policy（置信度 + 权限判断）
    → Period Resolver（相对时间 → 具体日期）
    → Tool Invocation（调用现有报告生成流程）
    → 组装 Response（含回答、假设、证据、建议追问）

Iteration 1 不调用 LLM 生成复杂自然语言回答，使用确定性模板。

架构位置：
    POST /api/v1/reports/assistant/messages
    → routers/report_assistant.py
    → ReportAssistantService.handle_message()
    → 受控 Python Tools
    → 现有报告编排链（Registry → Aggregator → Rules → Orchestrator）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from services.reporting.assistant.clarification import decide_clarification
from services.reporting.assistant.intent_parser import ReportIntentParser
from services.reporting.assistant.period_resolver import resolve_assistant_period
from services.reporting.assistant.prompts import (
    REPORT_KEYWORDS,
    build_report_catalog,
    get_allowed_report_types,
)
from services.reporting.assistant.schemas import (
    AssistantToolResult,
    EvidenceItem,
    ReportAssistantIntent,
    ReportAssistantMessageRequest,
    ReportAssistantMessageResponse,
    ReportConversationContext,
    ReportRequestPlan,
)
from services.reporting.assistant.tools import (
    tool_generate_existing_report,
    tool_get_application_risk_detail,
    tool_get_application_risk_items,
    tool_get_metric_trace,
    tool_get_report_data_quality,
    tool_get_report_detail,
    tool_query_report_status,
)
from services.reporting.orchestrator import generate_report_async
from services.reporting.registry import get_report_definition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 报告类型 → 中文描述映射（用于回答模板）
# ---------------------------------------------------------------------------

_REPORT_DESCRIPTIONS: dict[str, str] = {
    "application_risk": "申请风险情况",
    "sales_funnel": "销售漏斗转化情况",
    "channel_roi": "渠道ROI对比",
    "service_sla": "服务响应时效",
    "psych_weekly": "心理预警周报",
    "complaint_weekly": "投诉处理周报",
    "customer_ops": "客户经营分析",
    "daily_summary": "员工日报汇总",
    "weekly_summary": "综合经营周报",
    "action_closure": "行动闭环情况",
}


# ---------------------------------------------------------------------------
# Assistant Service
# ---------------------------------------------------------------------------


class ReportAssistantService:
    """智能报告助手总编排服务。

    每个请求实例化一次，通过 ``handle_message()`` 处理一轮对话。

    使用示例::

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(...),
            current_user=current_user,
            db=db,
        )
    """

    def __init__(self) -> None:
        self._intent_parser = ReportIntentParser()

    def handle_message(
        self,
        *,
        request: ReportAssistantMessageRequest,
        current_user: any,  # CurrentUser dataclass from utils.auth
        db: Session,
        background_tasks: BackgroundTasks | None = None,
    ) -> ReportAssistantMessageResponse:
        """处理一轮自然语言对话。

        完整流程：意图识别 → 澄清判断 → 时间解析 → 工具调用 → 组装响应。

        如果工具创建了新报告任务（status=pending/failed），通过 ``background_tasks``
        注册异步生成，不阻塞当前 HTTP 请求线程。

        Args:
            request: 用户请求（消息 + 会话上下文）。
            current_user: 当前登录用户（来自 utils.auth.CurrentUser）。
            db: 数据库会话。
            background_tasks: FastAPI BackgroundTasks，用于注册异步报告生成。
                为 None 时（如测试环境）跳过后台任务注册。

        Returns:
            ReportAssistantMessageResponse，包含回答、报告 ID、假设和更新后的上下文。
        """
        user_role = current_user.role_code or "employee"
        message = request.message.strip()
        context = request.conversation_context

        # ---- Step 1：获取允许的报告类型 ----
        catalog = build_report_catalog(user_role_code=user_role)
        allowed_types = {t.report_type for t in catalog if t.allowed}

        if not allowed_types:
            return self._build_response(
                status="permission_denied",
                intent=ReportAssistantIntent.UNKNOWN,
                answer="当前角色没有可访问的报告类型，请联系管理员。",
                needs_clarification=True,
                clarification_question="请确认你的账号权限配置。",
                confidence=0.0,
                context=context,
                error_code="NO_ACCESSIBLE_REPORT_TYPES",
            )

        # ---- Step 2：意图识别 ----
        plan = self._intent_parser.parse(
            message=message,
            allowed_report_types=catalog,
            context=context,
        )

        # ---- Step 3：澄清判断 ----
        clarification = decide_clarification(
            plan=plan,
            user_role=user_role,
            allowed_report_types=allowed_types,
        )

        if clarification.needs_clarification and not clarification.can_proceed:
            # 报告类型已识别但不在角色白名单时必须明确拒绝。不能把越权请求包装成
            # 普通澄清响应，否则 HTTP 层会返回 200，前端也无法执行安全隐藏策略。
            if plan.report_type and plan.report_type not in allowed_types:
                return self._build_response(
                    status="permission_denied",
                    intent=plan.intent,
                    answer="当前账号没有权限访问该类型的报告。",
                    needs_clarification=False,
                    confidence=0.0,
                    context=context,
                    error_code="PERMISSION_DENIED",
                )
            return self._build_response(
                status="needs_clarification",
                intent=plan.intent,
                answer=self._build_clarification_answer(plan, clarification),
                needs_clarification=True,
                clarification_question=clarification.clarification_question,
                confidence=clarification.confidence,
                context=context,
            )

        # ---- Step 4：时间解析（仅 GENERATE_REPORT 需要） ----
        # 多轮追问意图（drill_down/explain_risk/explain_metric/query_data_quality/
        # query_report_status）不需要时间解析，直接使用上下文中已有的 report 信息
        _MULTI_TURN_INTENTS = {
            ReportAssistantIntent.DRILL_DOWN,
            ReportAssistantIntent.EXPLAIN_RISK,
            ReportAssistantIntent.EXPLAIN_METRIC,
            ReportAssistantIntent.QUERY_DATA_QUALITY,
            ReportAssistantIntent.QUERY_REPORT_STATUS,
        }

        if plan.intent in _MULTI_TURN_INTENTS:
            # 多轮追问：跳过时间解析，使用 context 中的信息
            resolved = None
            all_assumptions = plan.assumptions
        else:
            # 生成报告：需要时间解析
            if plan.report_type is None:
                return self._build_response(
                    status="needs_clarification",
                    intent=plan.intent,
                    answer="请具体说明你想查看的报告类型。",
                    needs_clarification=True,
                    clarification_question="你想查看申请风险、销售漏斗、投诉处理还是其他报告？",
                    confidence=plan.confidence,
                    context=context,
                )

            definition = get_report_definition(plan.report_type)

            try:
                resolved = resolve_assistant_period(
                    relative_period=plan.relative_period,
                    period_start=plan.period_start,
                    period_end=plan.period_end,
                    report_definition=definition,
                    now=datetime.now(),
                )
            except ValueError as exc:
                return self._build_response(
                    status="needs_clarification",
                    intent=plan.intent,
                    answer=f"时间解析失败：{exc}",
                    needs_clarification=True,
                    clarification_question="请提供具体的时间范围，例如'上周'、'本月'。",
                    confidence=plan.confidence,
                    context=context,
                )

            all_assumptions = plan.assumptions + resolved.assumptions

        # ---- Step 5：工具调用 ----
        # 构建幂等键：client_request_id → manual:{key}
        idempotency_key = (
            f"manual:{request.client_request_id}"
            if request.client_request_id
            else None
        )

        tool_results = self._execute_tool(
            plan=plan,
            resolved_period=resolved,
            generated_by=current_user.id,
            idempotency_key=idempotency_key,
            db=db,
            current_user=current_user,
            context=context,
            message=message,
        )

        # 检查是否有工具返回了错误
        all_errors = [r for r in tool_results if r.status == "error"]
        all_success = [r for r in tool_results if r.status == "success"]

        if all_errors and not all_success:
            first_error = all_errors[0]
            err_status = "error"
            err_code = "TOOL_EXECUTION_FAILED"
            if "不存在" in (first_error.error or ""):
                err_status = "not_found"
                err_code = "REPORT_NOT_FOUND"
            elif "无权" in (first_error.error or ""):
                err_status = "permission_denied"
                err_code = "PERMISSION_DENIED"

            return self._build_response(
                status=err_status,
                intent=plan.intent,
                answer=f"处理失败：{first_error.error}",
                needs_clarification=False,
                confidence=plan.confidence,
                context=context,
                error_code=err_code,
            )

        # ---- Step 5b：注册后台异步生成（仅 GENERATE_REPORT） ----
        if plan.intent == ReportAssistantIntent.GENERATE_REPORT:
            gen_result = all_success[0] if all_success else None
            if gen_result:
                task_data = gen_result.data or {}
                is_new = task_data.get("created", False)
                task_status = task_data.get("status", "unknown")

                if is_new and task_status == "pending" and background_tasks is not None:
                    background_tasks.add_task(generate_report_async, gen_result.report_id)
                    logger.info(
                        "已注册后台报告生成任务: report_id=%d idempotency_key=%s",
                        gen_result.report_id,
                        idempotency_key,
                    )
                elif not is_new and task_status in ("pending", "generating"):
                    logger.info(
                        "幂等命中已有任务，跳过后台任务注册: report_id=%d status=%s",
                        gen_result.report_id,
                        task_status,
                    )

        # ---- Step 6：构建回答 ----
        # 使用 answer_composer 进行证据化回答
        primary_tool = all_success[0] if all_success else tool_results[0]
        primary_data = primary_tool.data if primary_tool.status == "success" else {}
        report_status = primary_data.get("status", "unknown") if isinstance(primary_data, dict) else "unknown"

        # 获取数据质量等级
        dq = primary_tool.data_quality
        dq_level = dq.get("level", "ok") if isinstance(dq, dict) else "ok"

        # 使用 answer_composer
        from services.reporting.assistant.answer_composer import compose_answer
        from services.reporting.assistant.config import settings as asst_settings

        composed = compose_answer(
            intent=plan.intent.value,
            tool_results=tool_results,
            data_quality_level=dq_level,
            llm_enabled=asst_settings.llm_enabled,
        )
        answer = composed["answer"]

        # ---- Step 7：更新上下文 ----
        # 从工具结果中提取 referenced_entities
        tool_entities: list[Any] = []
        for r in all_success:
            if isinstance(r.data, dict):
                refs = r.data.get("referenced_entities", [])
                if isinstance(refs, list):
                    tool_entities.extend(refs)

        updated_context = ReportConversationContext(
            conversation_id=context.conversation_id,
            last_report_id=primary_tool.report_id or context.last_report_id,
            last_report_type=plan.report_type or context.last_report_type,
            last_period_start=resolved.start if resolved else context.last_period_start,
            last_period_end=resolved.end if resolved else context.last_period_end,
            referenced_entities=tool_entities if tool_entities else context.referenced_entities,
            previous_intent=plan.intent,
        )

        # 确定响应状态
        if plan.intent == ReportAssistantIntent.GENERATE_REPORT:
            resp_status = "generating" if report_status in ("pending", "generating") else "completed"
        else:
            resp_status = "completed"

        return self._build_response(
            status=resp_status,
            intent=plan.intent,
            report_id=primary_tool.report_id,
            report_type=plan.report_type,
            answer=answer,
            needs_clarification=False,
            assumptions=all_assumptions,
            confidence=plan.confidence,
            context=updated_context,
            evidence=composed.get("evidence", []),
            suggested_follow_ups=composed.get("suggested_follow_ups", []),
            data_quality=primary_tool.data_quality,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _execute_tool(
        self,
        plan: ReportRequestPlan,
        resolved_period,
        generated_by: int,
        db: Session,
        idempotency_key: Optional[str] = None,
        current_user: Any = None,
        context: Optional[ReportConversationContext] = None,
        message: str = "",
    ) -> list[AssistantToolResult]:
        """根据意图选择并执行对应工具（Iteration 2A.1：返回工具结果列表）。

        Args:
            plan: 解析后的请求计划。
            resolved_period: 解析后的时间周期。
            generated_by: 当前用户 ID。
            db: 数据库会话。
            idempotency_key: 幂等键（可选）。
            current_user: 当前用户（用于权限检查）。
            context: 当前会话上下文。
            message: 用户原始消息（Iteration 2A.1：用于实体引用解析）。

        Returns:
            AssistantToolResult 列表（Iteration 2A 可能调用多个工具）。
        """
        report_id = plan.report_id or (context.last_report_id if context else None)

        # ---- QUERY_REPORT_STATUS ----
        if plan.intent == ReportAssistantIntent.QUERY_REPORT_STATUS:
            if not report_id:
                return [AssistantToolResult(
                    tool_name="query_report_status",
                    status="error",
                    error="没有关联的报告，请先生成一份报告",
                )]
            return [tool_query_report_status(
                report_id=report_id,
                current_user=current_user,
                db=db,
            )]

        # ---- GENERATE_REPORT ----
        if plan.intent == ReportAssistantIntent.GENERATE_REPORT and plan.report_type:
            definition = get_report_definition(plan.report_type)
            title = self._build_report_title(plan, resolved_period)
            return [tool_generate_existing_report(
                report_type=plan.report_type,
                period_start=resolved_period.start,
                period_end=resolved_period.end,
                generated_by=generated_by,
                title=title,
                idempotency_key=idempotency_key,
                db=db,
            )]

        # ---- DRILL_DOWN：获取最高风险项 ----
        if plan.intent == ReportAssistantIntent.DRILL_DOWN:
            if not report_id:
                return [AssistantToolResult(
                    tool_name="drill_down", status="error",
                    error="没有关联的报告，请先生成报告后再追问",
                )]
            # 先查状态
            status_result = tool_query_report_status(report_id=report_id, current_user=current_user, db=db)
            if status_result.data and status_result.data.get("status") != "completed" if isinstance(status_result.data, dict) else True:
                return [status_result]
            # 取风险明细
            return [tool_get_application_risk_items(
                report_id=report_id, limit=5, current_user=current_user, db=db,
            )]

        # ---- EXPLAIN_RISK：解释第一个申请的风险 ----
        if plan.intent == ReportAssistantIntent.EXPLAIN_RISK:
            if not report_id:
                return [AssistantToolResult(
                    tool_name="explain_risk", status="error",
                    error="没有关联的报告",
                )]
            # 使用原始用户消息解析实体引用（Iteration 2A.1 修正）
            from services.reporting.assistant.context import resolve_entity_reference
            entity = None
            if context and message:
                entity = resolve_entity_reference(
                    message=message,
                    context=context,
                )

            application_id = entity.entity_id if entity and entity.entity_type == "application" else None
            if not application_id:
                # 先取列表，再取第一个
                items_result = tool_get_application_risk_items(
                    report_id=report_id, limit=1, current_user=current_user, db=db,
                )
                if items_result.status == "success" and items_result.data:
                    items = items_result.data.get("items", []) if isinstance(items_result.data, dict) else []
                    if items:
                        application_id = str(items[0].get("application_id", ""))
                    else:
                        return [items_result]
                else:
                    return [items_result]

            if not application_id:
                return [AssistantToolResult(
                    tool_name="explain_risk", status="error",
                    error="无法确定要解释哪个申请",
                )]
            return [tool_get_application_risk_detail(
                report_id=report_id, application_id=application_id,
                current_user=current_user, db=db,
            )]

        # ---- EXPLAIN_METRIC：指标追溯 ----
        if plan.intent == ReportAssistantIntent.EXPLAIN_METRIC:
            if not report_id:
                return [AssistantToolResult(
                    tool_name="explain_metric", status="error",
                    error="没有关联的报告",
                )]
            # 从消息中提取指标名
            metric_name = plan.focus_metrics[0] if plan.focus_metrics else "风险分"
            return [tool_get_metric_trace(
                report_id=report_id, metric_name=metric_name,
                current_user=current_user, db=db,
            )]

        # ---- QUERY_DATA_QUALITY ----
        if plan.intent == ReportAssistantIntent.QUERY_DATA_QUALITY:
            if not report_id:
                return [AssistantToolResult(
                    tool_name="query_data_quality", status="error",
                    error="没有关联的报告",
                )]
            return [tool_get_report_data_quality(
                report_id=report_id, current_user=current_user, db=db,
            )]

        # ---- COMPARE_REPORTS：同类报告周期比较（Iteration 3） ----
        if plan.intent == ReportAssistantIntent.COMPARE_REPORTS and plan.report_type:
            from services.reporting.assistant.metric_catalog import list_metrics
            from services.reporting.assistant.tools import tool_compare_report_metrics
            from services.reporting.assistant.comparison_period import (
                resolve_comparison_period,
            )

            # 解析比较周期
            comparison_period = resolve_comparison_period(
                message, now=datetime.now(),
            )
            # 获取该报告类型的所有可用指标
            metrics = list_metrics(plan.report_type)
            metric_names = [m.metric_name for m in metrics]

            return [tool_compare_report_metrics(
                report_type=plan.report_type,
                comparison_period=comparison_period,
                metric_names=metric_names,
                current_user=current_user,
                db=db,
            )]

        # ---- CROSS_REPORT_ANALYSIS：受控跨报告分析（Iteration 3） ----
        if plan.intent == ReportAssistantIntent.CROSS_REPORT_ANALYSIS:
            from services.reporting.assistant.cross_report_catalog import (
                validate_cross_report_request,
            )
            from services.reporting.assistant.tools import tool_compare_report_metrics
            from services.reporting.assistant.comparison_period import (
                resolve_comparison_period,
            )

            # 从消息中检测两个报告类型
            detected_types = _detect_report_types_from_message(
                message, allowed_report_types=allowed_types,
            )
            if len(detected_types) < 2:
                return [AssistantToolResult(
                    tool_name="cross_report_analysis", status="error",
                    error="请指定两份要组合分析的报告，例如投诉处理和SLA一起分析",
                )]

            left_type, right_type = detected_types[0], detected_types[1]

            # 构建工具闭包和权限预检
            period = resolve_comparison_period(message, now=datetime.now())

            def _make_tool(report_type: str):
                metrics = list_metrics(report_type)
                metric_names = [m.metric_name for m in metrics]

                def _call():
                    result = tool_compare_report_metrics(
                        report_type=report_type,
                        comparison_period=period,
                        metric_names=metric_names,
                        current_user=current_user,
                        db=db,
                    )
                    return result
                return _call

            try:
                # validate_cross_report_request 校验权限后执行工具并返回结果
                executed_results = validate_cross_report_request(
                    left_type, right_type,
                    role_code=current_user.role_code or "employee",
                    permission_check=lambda rt: rt in allowed_types,
                    tool_calls=(_make_tool(left_type), _make_tool(right_type)),
                )
                # 将工具执行结果转换为 AssistantToolResult 列表
                return list(executed_results)
            except (ValueError, PermissionError) as exc:
                err_status = "permission_denied" if isinstance(exc, PermissionError) else "error"
                return [AssistantToolResult(
                    tool_name="cross_report_analysis",
                    status=err_status,
                    error=str(exc),
                )]

        # ---- 默认：查询已有报告 ----
        if report_id:
            return [tool_query_report_status(report_id=report_id, current_user=current_user, db=db)]

        return [AssistantToolResult(
            tool_name="no_op",
            status="error",
            error=f"不支持的意图: {plan.intent}",
        )]

    def _build_report_title(self, plan: ReportRequestPlan, resolved_period) -> str:
        """根据报告类型和周期构建报告标题。"""
        definition = get_report_definition(plan.report_type)
        label = definition.label
        start = resolved_period.start.isoformat()
        end = resolved_period.end.isoformat()
        return f"{label}（{start} ~ {end}）"

    def _build_answer(
        self,
        plan: ReportRequestPlan,
        tool_result: AssistantToolResult,
        assumptions: list[str],
    ) -> str:
        """使用确定性模板构建回答。Iteration 1 不调用 LLM。"""
        report_type = plan.report_type or ""
        description = _REPORT_DESCRIPTIONS.get(report_type, report_type)

        if tool_result.status == "success" and tool_result.tool_name == "query_report_status":
            status = tool_result.data.get("status", "unknown") if tool_result.data else "unknown"
            status_text = {
                "completed": "已完成",
                "generating": "正在生成",
                "pending": "等待生成",
                "failed": "生成失败",
            }.get(status, status)
            return f"报告 #{tool_result.report_id} 当前状态：{status_text}。"

        if tool_result.status == "success":
            report_id = tool_result.report_id
            period = ""
            if tool_result.data:
                period = f"（{tool_result.data.get('period_start', '')} ~ {tool_result.data.get('period_end', '')}）"
            answer = f"已创建{description}报告{period}。"
            if report_id:
                answer += f" 报告 ID 为 #{report_id}，可在报告详情中查看。"
            return answer

        return "处理请求时发生错误，请稍后重试。"

    def _build_evidence(self, tool_result: AssistantToolResult) -> list[EvidenceItem]:
        """从工具结果中提取证据项。"""
        evidence: list[EvidenceItem] = []
        if tool_result.status == "success" and tool_result.report_id:
            evidence.append(
                EvidenceItem(
                    source=tool_result.tool_name,
                    reference=f"report_id={tool_result.report_id}",
                    value=tool_result.report_id,
                )
            )
        return evidence

    def _build_follow_ups(self, report_type: Optional[str]) -> list[str]:
        """根据报告类型生成建议追问。"""
        follow_ups: dict[str, list[str]] = {
            "application_risk": [
                "最严重的是哪几个申请？",
                "高风险申请主要缺哪些材料？",
            ],
            "sales_funnel": [
                "哪个阶段转化最低？",
                "有哪些长期停滞的线索？",
            ],
            "channel_roi": [
                "哪个渠道 ROI 最高？",
                "是否有渠道成本为 0 的数据质量问题？",
            ],
        }
        return follow_ups.get(report_type or "", [])[:3]

    def _build_clarification_answer(
        self,
        plan: ReportRequestPlan,
        clarification,
    ) -> str:
        """构建需要澄清时的回答文本。"""
        if clarification.clarification_question:
            return clarification.clarification_question
        return "我还不能确定你的需求，请更具体地描述。"

    def _build_response(
        self,
        *,
        status: str,
        intent: ReportAssistantIntent,
        answer: str,
        needs_clarification: bool,
        confidence: float,
        context: ReportConversationContext,
        report_id: Optional[int] = None,
        report_type: Optional[str] = None,
        assumptions: Optional[list[str]] = None,
        clarification_question: Optional[str] = None,
        evidence: Optional[list[EvidenceItem]] = None,
        suggested_follow_ups: Optional[list[str]] = None,
        data_quality: Optional[dict] = None,
        error_code: Optional[str] = None,
    ) -> ReportAssistantMessageResponse:
        """构建标准响应对象。"""
        return ReportAssistantMessageResponse(
            status=status,
            intent=intent,
            report_id=report_id,
            report_type=report_type,
            answer=answer,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            assumptions=assumptions or [],
            confidence=confidence,
            evidence=evidence or [],
            suggested_follow_ups=suggested_follow_ups or [],
            conversation_context=context,
            data_quality=data_quality,
            error_code=error_code,
        )


# ── 跨报告类型检测辅助（Iteration 3 — Task 8） ──
def _detect_report_types_from_message(
    message: str,
    allowed_report_types: set[str],
) -> list[str]:
    """从用户消息中检测提及的报告类型，按在 allowed_report_types 中出现顺序返回。

    用于跨报告分析时从自然语言中提取两个报告类型标识。
    LLM 不允许指定未注册的组合类型，解析结果仍由 cross_report_catalog 校验。
    """
    import re
    message_lower = message.lower()

    # 报告类型关键词映射（与 prompts.py 保持一致）
    _REPORT_KEYWORDS: dict[str, list[str]] = {
        "complaint_weekly": ["投诉", "处理", "纠纷"],
        "service_sla": ["sla", "服务水平", "响应", "服务"],
        "sales_funnel": ["销售漏斗", "转化", "签约", "漏斗"],
        "customer_ops": ["客户经营", "客户", "运营", "流失"],
        "application_risk": ["申请风险", "风险", "申请"],
        "action_closure": ["行动闭环", "闭环", "行动", "完成率"],
        "channel_roi": ["渠道", "roi", "投入", "回报"],
    }

    scored: list[tuple[str, int]] = []
    for report_type in allowed_report_types:
        keywords = _REPORT_KEYWORDS.get(report_type, [report_type])
        score = sum(1 for kw in keywords if kw.lower() in message_lower)
        if score > 0:
            scored.append((report_type, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [rt for rt, _ in scored]
