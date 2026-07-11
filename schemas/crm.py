"""
意向客户 & 跟进记录 - Pydantic Schema
员工日报 - Pydantic Schema
"""
from __future__ import annotations

from typing import Literal, Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field


# ==================== 意向客户 ====================

class LeadCreate(BaseModel):
    """新增意向客户"""
    customer_name: str = Field(..., max_length=64, examples=["李四"])
    contact_info: Optional[str] = Field(None, max_length=128, examples=["139xxxx0002"])
    gender: Optional[str] = Field(None, max_length=10, examples=["M"])
    age: Optional[int] = Field(None, examples=[25])
    education_level: Optional[str] = Field(None, examples=["本科"])
    intended_country: Optional[str] = Field(None, examples=["英国,美国"])
    intended_major: Optional[str] = Field(None, examples=["计算机科学"])
    source_channel: Optional[str] = Field(None, examples=["线上"])
    background_info: Optional[str] = Field(None, examples=["对UCL计算机硕士感兴趣，GPA 3.5"])
    customer_profile_id: Optional[int] = Field(None, examples=[1])
    remark: Optional[str] = Field(None, examples=["高意向客户，需尽快跟进"])
    owner_employee_id: int = Field(..., examples=[2])


class LeadUpdate(BaseModel):
    """更新意向客户信息（部分更新：所有字段 Optional，只更新传了的字段）"""
    customer_name: Optional[str] = None
    # Optional + 默认 None = 可选字段，客户端可以不传
    contact_info: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    education_level: Optional[str] = None
    intended_country: Optional[str] = None
    intended_major: Optional[str] = None
    source_channel: Optional[str] = None
    background_info: Optional[str] = None
    customer_profile_id: Optional[int] = None
    remark: Optional[str] = None
    owner_employee_id: Optional[int] = None


class LeadStatusUpdate(BaseModel):
    """更新客户状态"""
    status: Literal["new", "contacting", "qualified", "signed", "lost"] = Field(
        ..., description="客户状态：new(新)/contacting(跟进中)/qualified(已确认)/signed(已签约)/lost(已流失)",
        examples=["contacting"])
    # Literal 类型：FastAPI 自动校验，传入非法值直接返回 422
    lost_reason: Optional[str] = Field(None, max_length=255, description="仅 lost 时填写",
                                       examples=["价格太高"])


class LeadResponse(BaseModel):
    """客户响应模型"""
    id: int
    customer_name: str
    contact_info: str
    gender: Optional[str] = None
    age: Optional[int] = None
    education_level: Optional[str] = None
    intended_country: Optional[str] = None
    intended_major: Optional[str] = None
    source_channel: Optional[str] = None
    background_info: Optional[str] = None
    remark: Optional[str] = None
    status: str
    lost_reason: Optional[str] = None
    owner_employee_id: Optional[int] = None
    customer_profile_id: Optional[int] = None
    owner_name: Optional[str] = None
    last_contact_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}
    # from_attributes=True：允许 model_validate(ORM对象) 直接从 ORM 属性读取数据
    # Pydantic v2 替代了 v1 的 class Config: orm_mode = True


class LeadListResponse(BaseModel):
    """客户列表响应（含分页）"""
    items: List[LeadResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ==================== 跟进记录 ====================

class FollowUpCreate(BaseModel):
    """新增跟进记录"""
    employee_id: int = Field(..., examples=[2])
    follow_type: Literal["phone", "wechat", "meeting", "email", "other"] = Field(
        ..., description="跟进方式：phone/wechat/meeting/email/other",
        examples=["wechat"])
    # Literal 限制只能选这5种跟进方式，FastAPI 自动校验
    content: str = Field(..., examples=["客户确认意向，下周面谈"])
    next_plan: Optional[str] = Field(None, max_length=255, examples=["安排线下咨询"])


class FollowUpResponse(BaseModel):
    """跟进记录响应"""
    id: int
    lead_id: int
    employee_id: int
    follow_type: str
    content: str
    next_plan: Optional[str] = None
    create_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==================== 员工日报 ====================

class DailyReportCreate(BaseModel):
    """提交日报"""
    employee_id: int = Field(..., examples=[2])
    report_date: date = Field(..., examples=["2025-03-20"])
    status: Literal["draft", "submitted"] = Field(
        "draft", description="日报状态：draft(草稿)/submitted(已提交)",
        examples=["draft"])
    raw_content: Optional[str] = Field(None, description="口述/输入原文",
                                       examples=["今天跟进了3个客户..."])
    # raw_content: 员工原始口述，content: LLM/AI 结构化后的版本
    # 如果只传 raw_content，后端会自动调用 LLM 结构化填充 content
    content: Optional[str] = Field(None, description="AI结构化后的文本（可由后端自动生成）")
    key_progress: Optional[List[str]] = Field(None, examples=[["签约1单", "新增2个意向"]])
    # key_progress 和 risks 是字符串数组，支持多条进展/风险
    risks: Optional[List[str]] = Field(None, examples=[["客户A可能流失"]])
    next_plan: Optional[str] = Field(None, examples=["明天跟进新客户"])


class DictateReportRequest(BaseModel):
    """口述日报请求：员工口述原文，由后端 AI 自动结构化后落库"""
    employee_id: int = Field(..., examples=[2], description="员工ID")
    report_date: date = Field(..., examples=["2025-03-20"], description="日报日期")
    raw_content: str = Field(..., min_length=1, description="口述/输入原文")
    status: Literal["draft", "submitted"] = Field(
        "draft",
        description="日报状态：draft(草稿)/submitted(已提交)",
        examples=["draft"],
    )


class DailyReportResponse(BaseModel):
    """日报响应"""
    id: int
    employee_id: int
    report_date: date
    status: str
    raw_content: Optional[str] = None
    content: str
    key_progress: Optional[List[str]] = None
    risks: Optional[List[str]] = None
    next_plan: Optional[str] = None
    create_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmployeeSummaryItem(BaseModel):
    """单个员工的日报汇总"""
    employee_id: int
    key_progress: Optional[List[str]] = None
    risks: Optional[List[str]] = None


class DailyReportSummaryResponse(BaseModel):
    """日报汇总响应（管理层用）"""
    report_date: date
    total_submitted: int
    employees: List[EmployeeSummaryItem]


class DailyReportManagementSummary(BaseModel):
    """管理层日报汇总响应（智能报告模块，含 AI 自然语言总览）"""
    report_date: date
    total_submitted: int
    employees: List[EmployeeSummaryItem]
    ai_overview: str = Field(
        "", description="AI 基于当日团队日报生成的整体工作总览文本（LLM 不可用时为空）"
    )


# ==================== 客户研判模块 ====================
# 以下 Schema 供 services/profile_service.py 和 routers/profile.py 使用
# 对应 models/crm.py 中的 ProfileRule / CustomerSource / CustomerProfile

class CustomerSourceResponse(BaseModel):
    """客户信息来源响应"""
    id: int
    source_type: str
    raw_content: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    parse_status: str
    parse_result: Optional[dict] = None
    parse_error: Optional[str] = None
    operator_id: Optional[int] = None
    create_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CustomerProfileResponse(BaseModel):
    """客户画像研判结果响应"""
    id: int
    customer_name: Optional[str] = None
    contact_info: Optional[str] = None
    source_id: Optional[int] = None
    background_info: Optional[dict] = None
    match_result: Optional[str] = None
    matched_product: Optional[str] = None
    match_score: Optional[float] = None
    match_reason: Optional[str] = None
    recommended_programs: Optional[list] = None
    evaluator_id: Optional[int] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProfileDetailResponse(BaseModel):
    """客户研判完整详情（来源 + 画像联合查询）"""
    # 来源信息
    source_id: int
    source_type: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    parse_status: str
    parse_error: Optional[str] = None
    # 画像信息（研判未完成时为 None）
    customer_name: Optional[str] = None
    contact_info: Optional[str] = None
    background_info: Optional[dict] = None
    match_result: Optional[str] = None
    matched_product: Optional[str] = None
    match_score: Optional[float] = None
    match_reason: Optional[str] = None
    recommended_programs: Optional[list] = None
    # 时间
    source_create_time: Optional[datetime] = None
    profile_update_time: Optional[datetime] = None


class ProfileRuleCreate(BaseModel):
    """创建画像研判规则"""
    product_line: str = Field(..., max_length=64, examples=["留学申请"])
    rule_name: str = Field(..., max_length=128, examples=["硕博连读-本科毕业生匹配规则"])
    rule_content: dict = Field(..., description="研判规则配置（JSON）")
    match_prompt: Optional[str] = Field(None, description="AI 研判系统提示词")
    priority: int = Field(0, description="优先级（数值越大越优先）")


class ProfileRuleUpdate(BaseModel):
    """更新画像研判规则（部分更新）"""
    product_line: Optional[str] = None
    rule_name: Optional[str] = None
    rule_content: Optional[dict] = None
    match_prompt: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[int] = Field(None, description="1=启用 0=禁用")


class ProfileRuleResponse(BaseModel):
    """画像研判规则响应"""
    id: int
    product_line: str
    rule_name: str
    rule_content: dict
    match_prompt: Optional[str] = None
    priority: int
    status: int
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnalyzeRequest(BaseModel):
    """触发 AI 研判请求"""
    rule_id: Optional[int] = Field(None, description="指定规则 ID（不填则自动按优先级匹配）")


# ==================== 智能助手模块 ====================
# 以下 Schema 供 services/assistant_service.py 和 routers/assistant.py 使用
# 对应 models/crm.py 中的 AssistantSession / AssistantMessage

class AssistantChatRequest(BaseModel):
    """智能助手聊天请求"""
    session_id: Optional[str] = Field(None, description="会话 ID（首次对话不传，后端自动生成）")
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")


class AssistantChatResponse(BaseModel):
    """智能助手聊天回复"""
    session_id: str
    reply_text: str
    action_type: Optional[str] = None  # text/sql/api
    action_data: Optional[dict] = None  # SQL 查询结果或 API 返回数据
    create_time: datetime

    model_config = {"from_attributes": True}


class AssistantSessionResponse(BaseModel):
    """智能助手会话响应"""
    id: int
    session_id: str
    employee_id: int
    status: str
    create_time: datetime
    last_message_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssistantMessageResponse(BaseModel):
    """智能助手消息响应"""
    id: int
    session_id: str
    role: str
    content: str
    action_type: Optional[str] = None
    action_detail: Optional[dict] = None
    action_result: Optional[dict] = None
    tokens_used: Optional[int] = None
    create_time: datetime

    model_config = {"from_attributes": True}
