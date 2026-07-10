"""
学生智能助手 — Pydantic 请求/响应 Schema

严格对齐数据库表字段名（snake_case），API 规范 V1.2 §2.6

命名规范 (API 规范 V1.2 §2.5):
    - 请求体: {Resource}Create / {Resource}Update
    - 响应体: {Resource}Response / {Resource}ListResponse
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# =============================================================================
# 请假管理 (student_admin_service 表)
# =============================================================================

class LeaveCreate(BaseModel):
    """提交请假申请 — POST /student/leave-requests"""
    student_id: int = Field(..., gt=0, description="学生ID → sys_user.id")
    service_type: str = Field(default="leave", description="服务类型: leave/exam_query/other")
    leave_type: str = Field(..., description="请假类型: sick/personal/emergency")
    start_time: str = Field(..., description="开始时间 (YYYY-MM-DD HH:mm)")
    end_time: str = Field(..., description="结束时间 (YYYY-MM-DD HH:mm)")
    reason: str = Field(..., min_length=1, max_length=2000, description="申请事由")
    attachment_url: Optional[str] = Field(None, max_length=512, description="附件URL")

    @field_validator("leave_type")
    @classmethod
    def validate_leave_type(cls, v):
        if v not in ("sick", "personal", "emergency"):
            raise ValueError("leave_type must be: sick / personal / emergency")
        return v

    @field_validator("service_type")
    @classmethod
    def validate_service_type(cls, v):
        if v not in ("leave", "exam_query", "other"):
            raise ValueError("service_type must be: leave / exam_query / other")
        return v


class LeaveApprove(BaseModel):
    """审批请假 — PUT /student/leave-requests/{id}/approve"""
    action: str = Field(..., description="审批动作: approve / reject")
    approver_id: int = Field(..., gt=0, description="审批人ID → sys_user.id")
    approval_comment: Optional[str] = Field(None, max_length=512, description="审批意见")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        if v not in ("approve", "reject"):
            raise ValueError("action must be: approve / reject")
        return v


class LeaveItemResponse(BaseModel):
    """请假记录响应"""
    id: int
    student_id: int
    service_type: str
    leave_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: str
    attachment_url: Optional[str] = None
    status: str
    approver_id: Optional[int] = None
    approval_comment: Optional[str] = None
    approval_time: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeaveListResponse(BaseModel):
    """请假记录列表"""
    total: int
    items: List[LeaveItemResponse]


# =============================================================================
# 售后反馈 (student_feedback_ticket 表)
# =============================================================================

class FeedbackCreate(BaseModel):
    """提交投诉/建议 — POST /student/feedback-tickets"""
    student_id: int = Field(..., gt=0, description="学生ID → sys_user.id")
    ticket_type: str = Field(default="complaint", description="工单类型: complaint/suggestion/consult")
    category: Optional[str] = Field(None, max_length=64, description="分类")
    title: Optional[str] = Field(None, max_length=255, description="工单标题")
    content: str = Field(..., min_length=1, max_length=5000, description="反馈内容")
    detail: Optional[str] = Field(None, description="详细描述")

    @field_validator("ticket_type")
    @classmethod
    def validate_ticket_type(cls, v):
        if v not in ("complaint", "suggestion", "consult"):
            raise ValueError("ticket_type must be: complaint / suggestion / consult")
        return v


class FeedbackUpdate(BaseModel):
    """处理投诉 — PUT /student/feedback-tickets/{id}"""
    status: str = Field(..., description="目标状态: processing/resolved/closed")
    assignee_id: Optional[int] = Field(None, gt=0, description="处理人ID → sys_user.id")
    solution: Optional[str] = Field(None, description="解决方案")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("processing", "resolved", "closed"):
            raise ValueError("status must be: processing / resolved / closed")
        return v


class FeedbackItemResponse(BaseModel):
    """工单响应"""
    id: int
    student_id: Optional[int] = None
    ticket_type: str
    category: Optional[str] = None
    title: Optional[str] = None
    content: str
    detail: Optional[str] = None
    status: str
    priority: str
    assignee_id: Optional[int] = None
    solution: Optional[str] = None
    satisfaction: Optional[int] = None
    is_notified: int = 0
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class FeedbackListResponse(BaseModel):
    """工单列表"""
    total: int
    items: List[FeedbackItemResponse]


# =============================================================================
# 心理健康 (student_psych_record / profile / alert 表)
# =============================================================================

class PsychRecordCreate(BaseModel):
    """记录心理交互 — POST /student/psych/record (Dify 白名单)"""
    student_id: int = Field(..., gt=0, description="学生ID → sys_user.id")
    emotion_tag: str = Field(..., description="情绪标签: 焦虑/低落/愤怒/平稳/积极")
    emotion_score: int = Field(..., ge=0, le=100, description="情绪分值 (0-100)")
    interaction_content: str = Field(..., description="交互内容摘要")
    trigger_keywords: Optional[List[str]] = Field(None, description="触发关键词")
    record_date: Optional[str] = Field(None, description="记录日期 (YYYY-MM-DD)")


class PsychRecordResponse(BaseModel):
    """心理记录写入结果"""
    id: int
    student_id: int
    emotion_tag: str
    emotion_score: int
    risk_level: str
    alert_created: bool = False
    alert_id: Optional[int] = None


class PsychAlertItemResponse(BaseModel):
    """心理预警响应"""
    id: int
    student_id: int
    trigger_reason: str
    risk_level: str
    status: str
    teacher_id: Optional[int] = None
    follow_record: Optional[str] = None
    resolved_time: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class PsychAlertListResponse(BaseModel):
    """心理预警列表"""
    total: int
    items: List[PsychAlertItemResponse]


class PsychAlertUpdate(BaseModel):
    """处理心理预警 — PUT /student/psych/alerts/{id}"""
    status: str = Field(..., description="目标状态: following/resolved/dismissed")
    teacher_id: int = Field(..., gt=0, description="负责老师ID → sys_user.id")
    follow_record: Optional[str] = Field(None, description="跟进记录")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("following", "resolved", "dismissed"):
            raise ValueError("status must be: following / resolved / dismissed")
        return v


# =============================================================================
# 申请进度 (application_progress 表)
# =============================================================================

class ApplicationItemResponse(BaseModel):
    """申请进度响应"""
    id: int
    student_id: int
    target_school: Optional[str] = None
    target_major: Optional[str] = None
    stage: Optional[str] = None
    progress_detail: Optional[str] = None
    deadline: Optional[str] = None
    next_action: Optional[str] = None
    handler_id: Optional[int] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApplicationListResponse(BaseModel):
    """申请进度列表"""
    total: int
    items: List[ApplicationItemResponse]


# =============================================================================
# 学业DDL (academic_deadline 表)
# =============================================================================

class DeadlineItemResponse(BaseModel):
    """学业DDL响应"""
    id: int
    student_id: Optional[int] = None
    deadline_type: str
    title: str
    description: Optional[str] = None
    deadline: str
    reminder_enabled: int = 1
    reminder_days: Optional[list] = None
    status: str = "pending"
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class DeadlineListResponse(BaseModel):
    """DDL列表"""
    total: int
    items: List[DeadlineItemResponse]


# =============================================================================
# 通用分页
# =============================================================================

class PaginationParams(BaseModel):
    """通用分页参数 — API 规范 V1.2 §12.1"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


# =============================================================================
# 通知中心 (student_notification 表)
# =============================================================================

class NotificationItemResponse(BaseModel):
    """通知条目响应"""
    id: int
    student_id: int
    notify_type: str
    title: str
    content: str
    related_type: Optional[str] = None
    related_id: Optional[int] = None
    is_read: int = 0
    create_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """通知列表"""
    total: int
    unread_count: int
    items: List[NotificationItemResponse]


# =============================================================================
# 增值转化 - 意向标签 (student_intent_tag 表)
# =============================================================================

class IntentCreate(BaseModel):
    """记录学生意向 — POST /student/intent"""
    student_id: int = Field(..., gt=0, description="学生ID → sys_user.id")
    intent_type: str = Field(..., description="意向类型: master/phd/transfer/consult/other")
    intent_name: Optional[str] = Field(None, max_length=128, description="意向名称")
    source: Optional[str] = Field("chat", description="来源: chat/feedback/progress/manual")
    score: Optional[int] = Field(None, ge=0, le=100, description="意向强度(0-100)")
    remark: Optional[str] = Field(None, description="备注")

    @field_validator("intent_type")
    @classmethod
    def validate_intent_type(cls, v):
        if v not in ("master", "phd", "transfer", "consult", "other"):
            raise ValueError("intent_type must be: master / phd / transfer / consult / other")
        return v


class IntentItemResponse(BaseModel):
    """意向标签响应"""
    id: int
    student_id: int
    intent_type: str
    intent_name: Optional[str] = None
    source: Optional[str] = None
    score: Optional[int] = None
    remark: Optional[str] = None
    create_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class IntentListResponse(BaseModel):
    """意向标签列表"""
    total: int
    items: List[IntentItemResponse]


class RecommendationResponse(BaseModel):
    """增值转化推荐项"""
    intent_type: str
    intent_name: Optional[str] = None
    matched_project: str
    score: Optional[int] = None
"""
基础设施模块 — Pydantic Schema
===========================================
用户、角色、组织架构相关的请求/响应数据结构。

包含:
  登录认证:
    LoginRequest        — 登录请求（username + password）
    TokenResponse       — 登录成功返回（Token + 用户信息）
    UserMeResponse      — 当前用户个人信息

  用户管理:
    UserCreate          — 创建用户请求
    UserUpdate          — 更新用户请求
    UserResponse        — 用户信息响应

  角色查询:
    RoleResponse        — 角色信息响应

  组织架构:
    OrganizationCreate  — 创建组织节点请求
    OrganizationResponse — 组织节点响应

⭐ 字段命名严格对齐数据库列名（API 文档第 2.6 节）:
  - real_name（非 display_name / name）
  - user_type（非 role）
  - contact_info（非 phone + email 拆分）
  - create_time（非 created_at）
  - update_time（非 updated_at）
  - org_name（非 name）
  - parent_id（非 parent_org_id）

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》
  - 第 4.2 节  POST /api/v1/auth/login  — 用户登录
  - 第 4.3 节  GET /api/v1/auth/me     — 当前用户信息
  - 第 2.6 节  字段命名与数据库对齐规范
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 一、登录认证 Schema
# ============================================================

class LoginRequest(BaseModel):
    """
    用户登录请求体。

    对应 API 文档第 4.2 节 POST /api/v1/auth/login。
    前端提交用户名和明文密码，后端用 bcrypt 校验。

    校验规则:
      - username: 必填，1-64 字符
      - password: 必填，1-128 字符（仅做长度校验，不对密码复杂度做强限制）
    """

    username: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="登录账号",
        examples=["admin"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="登录密码（明文，传输时应走 HTTPS）",
        examples=["123456"],
    )


class TokenResponse(BaseModel):
    """
    登录成功后返回的 Token + 用户概要。

    对应 API 文档第 4.2 节 POST /api/v1/auth/login 成功响应 data 部分。
    字段对齐 sys_user 表: user_id, username, real_name, user_type, role_id。
    """

    user_id: int = Field(..., description="用户主键（对应 sys_user.id）")
    username: str = Field(..., description="登录账号")
    real_name: str = Field(..., description="真实姓名（对应 sys_user.real_name）")
    user_type: str = Field(..., description="用户类型（student/employee/admin，对应 sys_user.user_type）")
    role_id: Optional[int] = Field(default=None, description="角色ID（对应 sys_user.role_id）")
    access_token: str = Field(..., description="JWT Token，后续请求放在 Authorization: Bearer {token}")
    token_type: str = Field(default="bearer", description="Token 类型，固定为 bearer")
    expires_in: int = Field(..., description="Token 有效期（秒），默认 86400 = 24小时")


class UserMeResponse(BaseModel):
    """
    当前登录用户的详细信息。

    对应 API 文档第 4.3 节 GET /api/v1/auth/me 成功响应 data 部分。
    字段完全对齐 sys_user 表列名。
    """

    user_id: int = Field(..., description="用户主键")
    username: str = Field(..., description="登录账号")
    real_name: str = Field(..., description="真实姓名")
    user_type: str = Field(..., description="用户类型")
    department: Optional[str] = Field(default=None, description="所属部门/院系")
    contact_info: Optional[str] = Field(default=None, description="联系方式")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL")
    status: str = Field(..., description="账号状态（normal/disabled）")


# ============================================================
# 二、用户管理 Schema
# ============================================================


class UserCreate(BaseModel):
    """
    创建用户请求体。

    字段对齐 sys_user 表必要字段。
    password 接收明文，Service 层用 bcrypt 哈希后存储。
    """

    username: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="登录账号（唯一，不能重复）",
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="登录密码（明文，将自动 bcrypt 哈希后入库）",
    )
    real_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="真实姓名",
    )
    user_type: str = Field(
        ...,
        pattern="^(student|employee|admin)$",  # 正则约束：只能是这三个值之一
        description="用户类型: student / employee / admin",
        examples=["employee"],
    )
    role_id: Optional[int] = Field(
        default=None,
        description="角色ID（逻辑关联 sys_role，可为空）",
    )
    department: Optional[str] = Field(
        default=None,
        max_length=128,
        description="所属部门/院系",
    )
    contact_info: Optional[str] = Field(
        default=None,
        max_length=128,
        description="联系方式（手机/邮箱）",
    )
    avatar_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="头像 URL",
    )


class UserUpdate(BaseModel):
    """
    更新用户请求体。

    所有字段均为可选——只传需要修改的字段。
    密码修改应走单独的"修改密码"接口（安全考虑），这里不包含 password 字段。
    """

    real_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="真实姓名",
    )
    user_type: Optional[str] = Field(
        default=None,
        pattern="^(student|employee|admin)$",
        description="用户类型",
    )
    role_id: Optional[int] = Field(
        default=None,
        description="角色ID（逻辑关联 sys_role）",
    )
    department: Optional[str] = Field(
        default=None,
        max_length=128,
        description="所属部门/院系",
    )
    contact_info: Optional[str] = Field(
        default=None,
        max_length=128,
        description="联系方式",
    )
    avatar_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="头像 URL",
    )
    status: Optional[str] = Field(
        default=None,
        pattern="^(normal|disabled)$",
        description="账号状态: normal（正常）/ disabled（禁用）",
    )


class UserResponse(BaseModel):
    """
    用户信息响应体。

    字段严格对齐 sys_user 表所有列名（API 文档第 2.6 节）。
    注意: 不返回 password_hash，密码哈希永远不对外暴露。
    """

    id: int = Field(..., description="主键")
    username: str = Field(..., description="登录账号")
    real_name: str = Field(..., description="真实姓名")
    user_type: str = Field(..., description="用户类型")
    role_id: Optional[int] = Field(default=None, description="角色ID")
    department: Optional[str] = Field(default=None, description="所属部门/院系")
    contact_info: Optional[str] = Field(default=None, description="联系方式")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL")
    status: str = Field(..., description="账号状态")
    create_time: datetime = Field(..., description="创建时间")
    update_time: datetime = Field(..., description="更新时间")

    # 允许从 ORM 对象直接构造
    model_config = {"from_attributes": True}


# ============================================================
# 三、角色查询 Schema
# ============================================================


class RoleResponse(BaseModel):
    """
    角色信息响应体。

    字段对齐 sys_role 表。
    role_code 是系统内部标识（如 "admin"），role_name 是前端展示名（如 "系统管理员"）。
    """

    id: int = Field(..., description="主键")
    role_code: str = Field(..., description="角色编码（admin/employee/manager/team_leader/student）")
    role_name: str = Field(..., description="角色名称")
    description: Optional[str] = Field(default=None, description="角色描述")
    status: int = Field(..., description="状态: 1=启用 0=禁用")
    create_time: datetime = Field(..., description="创建时间")
    update_time: datetime = Field(..., description="更新时间")

    model_config = {"from_attributes": True}


# ============================================================
# 四、组织架构 Schema
# ============================================================


class OrganizationCreate(BaseModel):
    """
    创建组织节点请求体。

    字段对齐 sys_organization 表。
    parent_id 为 None 表示根组织（树的顶层节点），非 None 表示某个组织的子节点。
    """

    org_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="组织名称",
    )
    parent_id: Optional[int] = Field(
        default=None,
        description="上级组织ID（逻辑关联 sys_organization，NULL=根节点）",
    )
    org_type: Optional[str] = Field(
        default=None,
        max_length=32,
        description="组织类型（如 company/department/team）",
    )
    sort_order: int = Field(
        default=0,
        description="同级排序权重（数值越小越靠前）",
    )


class OrganizationResponse(BaseModel):
    """
    组织节点响应体。

    字段对齐 sys_organization 表。
    children 字段用于返回树形结构（递归嵌套），仅在查询组织树时填充。
    """

    id: int = Field(..., description="主键")
    org_name: str = Field(..., description="组织名称")
    parent_id: Optional[int] = Field(default=None, description="上级组织ID")
    org_type: Optional[str] = Field(default=None, description="组织类型")
    sort_order: int = Field(..., description="排序权重")
    status: int = Field(..., description="状态: 1=启用 0=禁用")
    create_time: datetime = Field(..., description="创建时间")
    update_time: datetime = Field(..., description="更新时间")
    children: list["OrganizationResponse"] = Field(
        default_factory=list,
        description="子组织列表（树形结构，递归）",
    )

    model_config = {"from_attributes": True}


# ============================================================
# 五、密码修改 Schema
# ============================================================


class PasswordChangeRequest(BaseModel):
    """
    修改密码请求体。

    要求输入旧密码验证身份，新密码最少 6 位。
    """

    old_password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="当前密码（用于身份验证）",
    )
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="新密码（最少 6 位）",
    )
