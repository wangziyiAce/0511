"""智能报告模块 V2 - API Schema。

这个文件定义的是 FastAPI 请求体/响应体，不是数据库模型。

面试时可以这样讲：
“ORM 负责表结构，Schema 负责接口契约。报告模块 V2 把任务外壳和不同报告类型
的内容结构拆开，前端可以根据 report_type + schema_version 选择渲染器。”
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field

from services.reporting.registry import REPORT_REGISTRY
from services.reporting.schemas import REPORT_SCHEMA_VERSION


REPORT_TYPES: list[str] = list(REPORT_REGISTRY.keys())


class ReportGenerateRequest(BaseModel):
    """POST /api/v1/reports/generate 请求体。"""

    report_type: str = Field(..., description="报告类型编码")
    report_title: str = Field(
        ...,
        validation_alias=AliasChoices("report_title", "title"),
        min_length=1,
        max_length=255,
        description="报告标题；兼容前端传 title，也兼容后端内部字段 report_title",
    )
    period_start: Optional[date] = Field(default=None, description="统计周期开始")
    period_end: Optional[date] = Field(default=None, description="统计周期结束")
    filters: dict[str, Any] = Field(default_factory=dict, description="报告筛选条件")

    # 这里开启字段名回填，是为了让调用方既可以传前端友好的 title，
    # 也可以传数据库/响应一致的 report_title；服务层仍统一读取 report_title。
    model_config = {"populate_by_name": True}


class ReportTaskResponse(BaseModel):
    """报告任务创建后的轻量响应。"""

    id: int
    report_type: str
    report_title: str
    status: str
    schema_version: int = REPORT_SCHEMA_VERSION
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    trigger_source: str = "manual"
    generated_by: Optional[int] = None
    create_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportDetailResponse(ReportTaskResponse):
    """报告详情响应。"""

    report_content: Optional[dict[str, Any]] = None
    report_html: Optional[str] = None
    data_quality: Optional[dict[str, Any]] = None
    request_filters: Optional[dict[str, Any]] = None
    aggregated_data_snapshot: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_time: Optional[datetime] = None
    completed_time: Optional[datetime] = None
    retry_of_report_id: Optional[int] = None
    retry_count: int = 0


class ReportTypeResponse(BaseModel):
    """GET /api/v1/reports/types 返回的报告类型契约。"""

    report_type: str
    label: str
    schema_version: int
    allowed_roles: list[str]
    template_name: str
    default_period_rule: str
    available_filters: list[str]
    json_schema: dict[str, Any]


class ReportListResponse(BaseModel):
    items: list[ReportTaskResponse]
    total: int
    page: int
    page_size: int


class ReportScheduleCreate(BaseModel):
    report_type: str
    cron_expression: str = Field(..., description="五段 cron 表达式，例如 0 9 * * 1")
    enabled: int = 1
    timezone: str = "Asia/Shanghai"
    period_rule: str = "previous_week"
    title_template: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    recipients: dict[str, Any] = Field(default_factory=dict)


class ReportScheduleUpdate(BaseModel):
    cron_expression: Optional[str] = None
    enabled: Optional[int] = None
    timezone: Optional[str] = None
    period_rule: Optional[str] = None
    title_template: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    recipients: Optional[dict[str, Any]] = None


class ReportScheduleResponse(ReportScheduleCreate):
    id: int
    filters: Optional[dict[str, Any]] = None
    recipients: Optional[dict[str, Any]] = None
    created_by: Optional[int] = None
    last_run_time: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    next_run_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportActionCreate(BaseModel):
    suggestion_text: str = Field(
        ...,
        validation_alias=AliasChoices("suggestion_text", "suggestion"),
        description="从报告建议转成的行动内容；兼容前端传 suggestion",
    )
    risk_code: Optional[str] = None
    owner_id: Optional[int] = None
    due_time: Optional[datetime] = None
    target_value: Optional[Decimal] = None

    # 与报告标题类似，行动项内部字段叫 suggestion_text，
    # 但前端表单更常用 suggestion；这里统一在 Schema 层做兼容。
    model_config = {"populate_by_name": True}


class ReportActionUpdate(BaseModel):
    suggestion_text: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("suggestion_text", "suggestion"),
    )
    risk_code: Optional[str] = None
    owner_id: Optional[int] = None
    due_time: Optional[datetime] = None
    status: Optional[str] = None
    target_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    completed_time: Optional[datetime] = None

    model_config = {"populate_by_name": True}


class ReportActionResponse(ReportActionCreate):
    id: int
    report_id: int
    status: str
    actual_value: Optional[Decimal] = None
    completed_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApplicationMaterialCreate(BaseModel):
    application_id: int
    student_id: Optional[int] = None
    owner_id: Optional[int] = None
    material_name: str
    required: int = Field(
        default=1,
        validation_alias=AliasChoices("required", "is_required"),
        description="是否必填；兼容前端传 is_required",
    )
    deadline: Optional[date] = None
    submitted_time: Optional[datetime] = None
    status: str = "pending"

    model_config = {"populate_by_name": True}


class ChannelCostCreate(BaseModel):
    channel: str
    cost_date: date = Field(
        ...,
        validation_alias=AliasChoices("cost_date", "spend_date"),
        description="投放/成本日期；兼容前端传 spend_date",
    )
    campaign: Optional[str] = None
    cost_amount: Decimal = Field(
        ...,
        validation_alias=AliasChoices("cost_amount", "cost"),
        description="渠道成本；兼容前端传 cost",
    )

    model_config = {"populate_by_name": True}


class CustomerContractCreate(BaseModel):
    customer_id: int
    lead_id: Optional[int] = None
    channel: Optional[str] = None
    contract_amount: Decimal
    signed_time: Optional[datetime] = None
    status: str = "signed"


class CustomerPaymentCreate(BaseModel):
    contract_id: int
    payment_amount: Decimal
    payment_time: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("payment_time", "paid_time"),
        description="回款时间；兼容前端传 paid_time",
    )
    status: str = "paid"

    model_config = {"populate_by_name": True}


class CRMLeadStatusUpdate(BaseModel):
    old_status: Optional[str] = None
    new_status: str
    change_reason: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("change_reason", "reason"),
        description="阶段变更原因；兼容前端传 reason",
    )

    model_config = {"populate_by_name": True}


class FeedbackTicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    owner_id: Optional[int] = None
    first_response_time: Optional[datetime] = None
    resolved_time: Optional[datetime] = None
    satisfaction_score: Optional[int] = None
