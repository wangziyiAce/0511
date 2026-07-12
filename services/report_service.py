"""
智能报告服务
负责：口述日报（AI 结构化）、管理层日报查阅与汇总
复用 services.crm_service.EmployeeService 的日报 CRUD 与汇总能力，
并接入 LLM 完成"口述原文 -> 结构化日报"的转换（对应需求：口述日报 / 管理日报查阅）。
"""
import json
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from models.crm import EmployeeDailyReport
from schemas.crm import (
    DailyReportCreate,
    DailyReportSummaryResponse,
    DailyReportManagementSummary,
    EmployeeSummaryItem,
)
from services.crm_service import EmployeeService, ParamError

# 复用智能助手模块已封装好的 LLM 调用能力（模块级函数），避免重复实现
from services.assistant_service import (
    _call_llm,
    _extract_json,
    is_llm_available,
)

logger = logging.getLogger(__name__)


# 口述结构化提示词：把自由口述整理为结构化日报
_STRUCTURE_SYSTEM_PROMPT = """你是一个企业工作日报的结构化整理助手。
根据员工口述的当日工作原文，提取并整理为结构化日报。
要求：
1. content：结构化的日报正文，概括今日完成的主要工作（条理清晰，可使用要点）。
2. key_progress：今日关键进展/成果，字符串数组，最多 5 条；没有则空数组。
3. risks：风险、阻碍或需关注的问题，字符串数组；没有则空数组。
4. next_plan：明日计划，一句话概括；没有则空字符串。

只输出如下 JSON，不要任何额外说明：
{
  "content": "结构化日报正文",
  "key_progress": ["进展1", "进展2"],
  "risks": ["风险1"],
  "next_plan": "明日计划"
}
"""

# 管理层总览提示词：把团队汇总浓缩成一段自然语言总览
_OVERVIEW_SYSTEM_PROMPT = """你是一个管理层的日报总览助手。
给定某日团队的日报汇总数据（各员工的关键进展与风险），
用一段简洁的中文（3-5 句）总结整体工作进度、亮点与需关注的风险，
帮助管理层快速感知团队状态。不要使用 markdown 标题，直接输出段落文本。
"""


class ReportService:
    """智能报告业务逻辑：口述日报 + 管理层查阅"""

    def __init__(self, db: Session):
        self.db = db
        # 组合复用员工日报的 CRUD 与汇总能力，不在本服务内重写
        self._employee_service = EmployeeService(db)

    # ============================================================
    # 一、口述日报：AI 自动识别核心内容 -> 结构化日报
    # ============================================================
    def dictate_report(
        self,
        employee_id: int,
        report_date: date,
        raw_content: str,
        status: str = "draft",
    ) -> EmployeeDailyReport:
        """
        口述日报主流程：将员工口述原文经 LLM 转换为结构化日报并落库。

        - raw_content 必填，为员工口述/输入的原文
        - LLM 可用时：提取 content / key_progress / risks / next_plan
        - LLM 不可用时：优雅降级为 content=raw_content，其余字段留空
        - 落库与校验（同日唯一、日期、员工存在性）委托 EmployeeService
        """
        if not raw_content or not raw_content.strip():
            raise ParamError("raw_content 不能为空（口述内容）")

        structured = self._structure_raw_content(raw_content)

        # 组装日报数据：结构化成功则用 AI 结果，失败则降级为原文
        data = DailyReportCreate(
            employee_id=employee_id,
            report_date=report_date,
            status=status,
            raw_content=raw_content,
            content=structured["content"] if structured else raw_content,
            key_progress=structured.get("key_progress") if structured else None,
            risks=structured.get("risks") if structured else None,
            next_plan=structured.get("next_plan") if structured else None,
        )
        logger.info(
            "口述日报：employee=%d date=%s llm=%s",
            employee_id, report_date, "on" if structured else "off(degraded)",
        )
        return self._employee_service.create_report(data)

    def _structure_raw_content(self, raw_content: str) -> Optional[dict]:
        """
        调用 LLM 将口述原文结构化。
        任一环节失败都返回 None，由调用方负责降级处理。
        """
        if not is_llm_available():
            return None
        try:
            raw_text = _call_llm(_STRUCTURE_SYSTEM_PROMPT, raw_content)
            if not raw_text:
                return None
            parsed = _extract_json(raw_text)
            if not parsed:
                return None
            # 兜底字段类型，保证返回结构稳定可被模型消费
            return {
                "content": str(parsed.get("content") or raw_content),
                "key_progress": parsed.get("key_progress") or [],
                "risks": parsed.get("risks") or [],
                "next_plan": parsed.get("next_plan") or "",
            }
        except Exception as e:  # noqa: BLE001 - LLM 解析异常统一降级
            logger.warning("口述结构化失败，降级为原文: %s", e)
            return None

    # ============================================================
    # 二、管理日报查阅：查询与汇总
    # ============================================================
    def list_reports(
        self,
        employee_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[EmployeeDailyReport]:
        """条件查询日报列表（委托 EmployeeService 实现）。"""
        return self._employee_service.list_reports(
            employee_id=employee_id,
            start_date=start_date,
            end_date=end_date,
        )

    def get_management_summary(
        self,
        report_date: date,
    ) -> DailyReportManagementSummary:
        """
        管理层日报汇总：
        1. 复用 EmployeeService.get_summary 取结构化汇总（提交数 + 每人关键进展/风险）
        2. 可选调用 LLM 生成一段自然语言总览 ai_overview（不可用则为空串）
        """
        base: DailyReportSummaryResponse = self._employee_service.get_summary(
            report_date=report_date
        )
        ai_overview = self._generate_overview(base)
        return DailyReportManagementSummary(
            report_date=base.report_date,
            total_submitted=base.total_submitted,
            employees=base.employees,
            ai_overview=ai_overview,
        )

    def _generate_overview(self, summary: DailyReportSummaryResponse) -> str:
        """基于日报汇总数据生成自然语言总览；LLM 不可用时返回空串。"""
        if not is_llm_available():
            return ""
        try:
            payload = json.dumps(
                [
                    {
                        "employee_id": e.employee_id,
                        "key_progress": e.key_progress or [],
                        "risks": e.risks or [],
                    }
                    for e in summary.employees
                ],
                ensure_ascii=False,
            )
            overview = _call_llm(_OVERVIEW_SYSTEM_PROMPT, payload)
            return overview.strip() if overview else ""
        except Exception as e:  # noqa: BLE001 - 总览生成失败不影响汇总返回
            logger.warning("生成管理层总览失败: %s", e)
            return ""
