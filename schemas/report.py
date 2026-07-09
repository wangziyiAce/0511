"""
智能报告模块 — Pydantic Schema
===========================================
请求体与响应体定义，严格对齐:
  《教育服务系统_API接口设计规范文档_V1.2》第 8 章 — 智能报告模块接口
  《教育服务系统_数据库设计规范文档_V2.1》第 6.7.1 节 — report_generation 表

字段命名原则:
  JSON 字段名与数据库表字段名严格对齐（snake_case），
  前端无需做字段名翻译。

Schema 清单:
  - ReportGenerateRequest    → POST /reports/generate 请求体
  - ReportResponse           → GET /reports/{id} 响应
  - ReportListQuery          → GET /reports 查询参数
  - ReportItem               → 报告列表中的单条记录
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import date, datetime

from schemas.common import PaginationParams


# ==================== 报告类型常量 ====================

# 严格对齐 report_generation 表的 ENUM 定义
REPORT_TYPES: list[str] = [
    "customer_ops",      # 全域客户经营分析
    "daily_summary",     # 员工日报汇总
    "weekly_summary",    # 综合周报
    "psych_weekly",      # 学生心理周报
    "complaint_weekly",  # 投诉处理周报
]

# 报告类型中文标签映射
REPORT_TYPE_LABELS: dict[str, str] = {
    "customer_ops": "全域客户经营分析",
    "daily_summary": "员工日报汇总",
    "weekly_summary": "综合周报",
    "psych_weekly": "学生心理周报",
    "complaint_weekly": "投诉处理周报",
}


# ==================== 请求体 ====================

class ReportGenerateRequest(BaseModel):
    """
    触发报告生成请求体（对齐 API 文档 8.2 节）

    字段对齐 report_generation 表:
      report_type  → report_type (ENUM)
      report_title → report_title (VARCHAR)
      period_start → period_start (DATE)
      period_end   → period_end (DATE)
    """

    report_type: str = Field(
        ...,
        description=f"报告类型: {', '.join(REPORT_TYPES)}",
        examples=["daily_summary"],
    )
    report_title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="报告标题，如'2026年7月第1周日报汇总'",
        examples=["2026年7月第1周日报汇总"],
    )
    period_start: Optional[date] = Field(
        default=None,
        description="统计周期起始日期",
        examples=["2026-07-01"],
    )
    period_end: Optional[date] = Field(
        default=None,
        description="统计周期截止日期",
        examples=["2026-07-07"],
    )


# ==================== 响应体 ====================

class ReportContent(BaseModel):
    """
    报告结构化内容（对齐 API 文档 8.3 节）

    对应 report_generation.report_content (JSON) 的结构约束。
    这是 Dify 生成报告时必须遵循的输出格式。
    """

    summary: Optional[str] = Field(
        default=None,
        description="报告摘要，概括整体情况",
    )
    key_findings: Optional[list[str]] = Field(
        default_factory=list,
        description="关键发现列表",
    )
    risks: Optional[list[str]] = Field(
        default_factory=list,
        description="风险预警列表",
    )
    suggestions: Optional[list[str]] = Field(
        default_factory=list,
        description="改进建议列表",
    )


class ReportResponse(BaseModel):
    """
    报告详情响应（对齐 API 文档 8.3 节）

    字段严格对齐 report_generation 表的所有字段。
    report_content 为 JSON 对象，report_html 为 HTML 字符串。
    """

    id: int = Field(..., description="报告 ID")
    report_type: str = Field(..., description="报告类型")
    report_title: str = Field(..., description="报告标题")
    report_content: Optional[dict] = Field(
        default=None,
        description="报告结构化内容（JSON）",
    )
    report_html: Optional[str] = Field(
        default=None,
        description="报告 HTML 渲染内容",
    )
    period_start: Optional[date] = Field(
        default=None,
        description="统计周期起始",
    )
    period_end: Optional[date] = Field(
        default=None,
        description="统计周期结束",
    )
    generated_by: Optional[int] = Field(
        default=None,
        description="生成人 ID",
    )
    status: str = Field(
        ...,
        description="生成状态: generating / completed / failed",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="失败原因（仅 status=failed 时有值）",
    )
    create_time: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class ReportItem(BaseModel):
    """
    报告列表中的单条记录（精简字段，不含大文本）

    列表接口不需要返回 report_content 和 report_html 大字段，
    前端点击详情时再单独请求 GET /reports/{id} 获取完整内容。
    """

    id: int = Field(..., description="报告 ID")
    report_type: str = Field(..., description="报告类型")
    report_title: str = Field(..., description="报告标题")
    period_start: Optional[date] = Field(default=None, description="统计周期起始")
    period_end: Optional[date] = Field(default=None, description="统计周期结束")
    generated_by: Optional[int] = Field(default=None, description="生成人 ID")
    status: str = Field(..., description="生成状态")
    error_message: Optional[str] = Field(default=None, description="失败原因")
    create_time: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


# ==================== 列表查询参数 ====================

class ReportListQuery(PaginationParams):
    """
    报告列表查询参数（对齐 API 文档 8.1 节）

    支持按报告类型、状态、时间范围筛选，支持分页。
    """

    report_type: Optional[str] = Field(
        default=None,
        description=f"报告类型筛选: {', '.join(REPORT_TYPES)}",
    )
    status: Optional[str] = Field(
        default=None,
        description="状态筛选: generating / completed / failed",
    )
    start_date: Optional[date] = Field(
        default=None,
        description="创建时间起始",
    )
    end_date: Optional[date] = Field(
        default=None,
        description="创建时间截止",
    )
