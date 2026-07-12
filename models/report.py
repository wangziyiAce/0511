"""智能报告模块 V2 - ORM 数据模型。

这个文件是智能报告模块的数据底座。V1 只有“报告生成记录”和“定时任务”
两张表，适合演示，但不适合做管理分析系统。V2 在保留旧能力的基础上补齐：

1. ``report_generation``：每一次生成任务的完整生命周期。
   它记录谁触发、什么时候开始、是否来自定时计划、是否重试、聚合快照、
   Schema 版本、错误码和完成时间。
2. ``report_schedule``：定时报告计划。
   独立 APScheduler 进程和手动接口都调用同一套编排层，通过“计划 ID + 周期”
   形成幂等键，避免一个周期重复生成。
3. 最小事实表：
   申请材料、CRM 阶段历史、渠道成本、合同、回款、报告行动项。
   这些表让新增的 5 类高价值报告有可追溯的数据来源。

项目约定：
-------
本项目延续“无物理外键”策略。也就是说，字段名会使用 ``customer_id``、
``owner_id``、``schedule_id`` 这类逻辑关联字段，并创建索引，但不使用
``ForeignKey``。原因是培训项目后续可能涉及数据导入、拆库、迁移和测试数据
重建，物理外键会提高耦合度。对应的数据存在性校验放在 Service 层完成。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, Index, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from models.student import StudentFeedbackTicket as CanonicalStudentFeedbackTicket
from models.student import StudentPsychAlert as CanonicalStudentPsychAlert
from utils.database import Base


REPORT_STATUS_VALUES = ("pending", "generating", "completed", "failed")
TRIGGER_SOURCE_VALUES = ("manual", "schedule", "retry", "system")

# 生产 MySQL 需要 MEDIUMTEXT 保存完整 HTML；SQLite 测试环境不认识该方言专有类型，
# 因此退化为等价的 Text。字段语义和 MySQL 建表类型都不会改变。
REPORT_HTML_TYPE = MEDIUMTEXT().with_variant(Text(), "sqlite")


class ReportGeneration(Base):
    """报告生成记录表。

    一条记录对应一次“报告生成尝试”，而不是一个永远被覆盖的报告。
    这样设计的好处是：

    * 失败原因可以保留下来，便于排查；
    * 重试会创建新记录，通过 ``retry_of_report_id`` 指向原失败记录；
    * 定时任务可以通过 ``idempotency_key`` 防止重复触发；
    * ``aggregated_data_snapshot`` 保存 SQL/规则引擎算出的指标快照，便于追溯。

    隐私边界：
    ``aggregated_data_snapshot`` 只保存聚合结果，不保存心理咨询原文、投诉原文等
    敏感长文本。心理报告只允许统计情绪趋势、预警等级、处理时效。
    """

    __tablename__ = "report_generation"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    report_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="报告类型编码，V2 改为 VARCHAR 以支持扩展",
    )
    report_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="报告标题",
    )
    report_content: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="按 report_type 区分的结构化报告内容",
    )
    report_html: Mapped[Optional[str]] = mapped_column(
        REPORT_HTML_TYPE,
        default=None,
        comment="后端模板渲染后的 HTML，禁止模型直接输出任意 HTML",
    )
    period_start: Mapped[Optional[date]] = mapped_column(
        Date,
        default=None,
        comment="统计周期开始日期",
    )
    period_end: Mapped[Optional[date]] = mapped_column(
        Date,
        default=None,
        comment="统计周期结束日期",
    )
    status: Mapped[str] = mapped_column(
        Enum(*REPORT_STATUS_VALUES, name="report_generation_status"),
        nullable=False,
        default="pending",
        comment="任务状态 pending/generating/completed/failed",
    )
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        comment="报告内容结构版本；历史数据为 1，新报告为 2",
    )
    # ---- 任务来源与重试链路 ----
    generated_by: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="触发生成的用户 ID，逻辑关联 sys_user.id",
    )
    schedule_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="定时计划 ID，逻辑关联 report_schedule.id",
    )
    retry_of_report_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="如果是重试，记录原失败报告 ID",
    )
    trigger_source: Mapped[str] = mapped_column(
        Enum(*TRIGGER_SOURCE_VALUES, name="report_generation_trigger_source"),
        nullable=False,
        default="manual",
        comment="触发来源 manual/schedule/retry/system",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前记录对应第几次尝试；原始任务为 0",
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        default=None,
        comment="幂等键；手动接口取请求头，定时任务取 schedule_id+period",
    )

    # ---- 请求、快照与质量说明 ----
    request_filters: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="生成报告时传入的筛选条件",
    )
    aggregated_data_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="SQL/规则引擎生成的聚合指标快照，不保存心理咨询原文",
    )
    data_quality: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="数据质量说明：缺失数据源、空数据、降级生成等",
    )

    # ---- 错误与生命周期时间 ----
    error_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        default=None,
        comment="机器可读错误码，例如 DIFY_SCHEMA_INVALID",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        default=None,
        comment="人类可读失败原因",
    )
    started_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=None,
        comment="任务真正开始生成的时间",
    )
    completed_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=None,
        comment="任务完成或失败的时间",
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_report_generation_type", "report_type"),
        Index("idx_report_generation_status", "status"),
        Index("idx_report_generation_period", "period_start", "period_end"),
        Index("idx_report_generation_generated_by", "generated_by"),
        Index("idx_report_generation_schedule", "schedule_id"),
        Index("idx_report_generation_retry_of", "retry_of_report_id"),
        Index("uk_report_generation_idempotency", "idempotency_key", unique=True),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "智能报告生成记录表",
        },
    )


class ReportSchedule(Base):
    """定时报告计划表。

    APScheduler 只负责“按 cron 唤醒”，真正创建报告任务仍走 orchestrator。
    这样手动生成、重试、定时生成都能复用同一套权限、幂等、聚合、AI、渲染逻辑。
    """

    __tablename__ = "report_schedule"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="报告类型编码")
    cron_expression: Mapped[str] = mapped_column(String(64), nullable=False, comment="五段 cron 表达式")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="1=启用，0=停用")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai", comment="计划时区")
    period_rule: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="previous_week",
        comment="统计周期规则 previous_day/previous_week/previous_month",
    )
    title_template: Mapped[Optional[str]] = mapped_column(
        String(255),
        default=None,
        comment="标题模板，可使用 {start}/{end}/{report_type}",
    )
    filters: Mapped[Optional[dict]] = mapped_column(JSON, default=None, comment="定时任务默认筛选条件")
    recipients: Mapped[Optional[dict]] = mapped_column(JSON, default=None, comment="通知接收人配置")
    created_by: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="创建计划的用户 ID，逻辑关联 sys_user.id",
    )
    last_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="最近运行时间")
    last_status: Mapped[Optional[str]] = mapped_column(String(32), default=None, comment="最近运行状态")
    last_error: Mapped[Optional[str]] = mapped_column(Text, default=None, comment="最近运行错误")
    next_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="下次运行时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_report_schedule_type", "report_type"),
        Index("idx_report_schedule_enabled", "enabled"),
        Index("idx_report_schedule_next_run", "next_run_time"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "智能报告定时计划表",
        },
    )


class ApplicationMaterialItem(Base):
    """申请材料明细表。

    新增 ``application_risk`` 报告需要知道：
    哪些材料是必填、截止日期是什么、是否已经提交、谁负责。
    """

    __tablename__ = "application_material_item"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    application_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="申请记录 ID")
    student_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="学生 ID")
    owner_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="负责人 ID")
    material_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="材料名称")
    required: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否必填 1/0")
    deadline: Mapped[Optional[date]] = mapped_column(Date, default=None, comment="材料截止日期")
    submitted_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="提交时间")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", comment="pending/submitted/waived")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_material_application", "application_id"),
        Index("idx_material_student", "student_id"),
        Index("idx_material_owner", "owner_id"),
        Index("idx_material_deadline", "deadline"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "申请材料明细表",
        },
    )


class CRMLeadStatusHistory(Base):
    """CRM 阶段变化历史表。

    ``sales_funnel`` 不能只看客户当前状态，还要看客户从哪个阶段流到哪个阶段、
    每个阶段停留多久、哪个顾问操作了变化。
    """

    __tablename__ = "crm_lead_status_history"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    lead_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="线索/客户 ID")
    old_status: Mapped[Optional[str]] = mapped_column(String(64), default=None, comment="变更前状态")
    new_status: Mapped[str] = mapped_column(String(64), nullable=False, comment="变更后状态")
    operator_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="操作人 ID")
    change_reason: Mapped[Optional[str]] = mapped_column(String(255), default=None, comment="变更原因")
    change_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="变更时间")

    __table_args__ = (
        Index("idx_lead_status_history_lead", "lead_id"),
        Index("idx_lead_status_history_time", "change_time"),
        Index("idx_lead_status_history_operator", "operator_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "CRM 客户阶段变化历史表",
        },
    )


class MarketingChannelCost(Base):
    """市场渠道成本表。

    ``channel_roi`` 报告的成本必须来自这里，不能由 AI 估算。
    """

    __tablename__ = "marketing_channel_cost"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    channel: Mapped[str] = mapped_column(String(64), nullable=False, comment="渠道名称")
    cost_date: Mapped[date] = mapped_column(Date, nullable=False, comment="投放日期")
    campaign: Mapped[Optional[str]] = mapped_column(String(128), default=None, comment="活动名称")
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="投放成本")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_channel_cost_channel_date", "channel", "cost_date"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "市场渠道投放成本表",
        },
    )


class CustomerContract(Base):
    """客户合同表。

    渠道 ROI 不只看签约数量，还要看合同金额和合同状态。
    """

    __tablename__ = "customer_contract"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    customer_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="客户 ID")
    lead_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="线索 ID")
    channel: Mapped[Optional[str]] = mapped_column(String(64), default=None, comment="归因渠道")
    contract_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="合同金额")
    signed_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="签约时间")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="signed", comment="signed/cancelled/refunded")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_contract_customer", "customer_id"),
        Index("idx_contract_channel_time", "channel", "signed_time"),
        Index("idx_contract_status", "status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "客户合同表",
        },
    )


class CustomerPayment(Base):
    """客户回款表。

    ROI 公式使用“实际回款”，不是合同金额，因此需要单独记录付款流水。
    """

    __tablename__ = "customer_payment"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    contract_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="合同 ID")
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="回款金额")
    payment_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="回款时间")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="paid", comment="paid/refunded/pending")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_payment_contract", "contract_id"),
        Index("idx_payment_time", "payment_time"),
        Index("idx_payment_status", "status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "客户回款表",
        },
    )


class ReportAction(Base):
    """报告行动项表。

    AI 报告只给“建议”还不够，管理闭环需要把建议转成行动：
    谁负责、什么时候完成、完成结果如何、目标值是否达成。
    """

    __tablename__ = "report_action"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    report_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, comment="报告 ID")
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False, comment="报告建议内容")
    risk_code: Mapped[Optional[str]] = mapped_column(String(64), default=None, comment="风险编码，用于识别重复问题")
    owner_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="责任人 ID")
    due_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="截止时间")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", comment="pending/confirmed/done/cancelled")
    target_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), default=None, comment="目标值")
    actual_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), default=None, comment="实际结果")
    completed_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="完成时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_report_action_report", "report_id"),
        Index("idx_report_action_owner", "owner_id"),
        Index("idx_report_action_status", "status"),
        Index("idx_report_action_risk_code", "risk_code"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "报告行动闭环表",
        },
    )


class _LegacyStudentFeedbackTicket(Base):
    """投诉/反馈工单最小模型。

    原计划要求给投诉工单增加 ``first_response_time`` 和 ``resolved_time``。
    本模型保留最小字段，既能支持 SLA 报告，也能给维护接口做演示。
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    student_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="学生 ID")
    ticket_type: Mapped[str] = mapped_column(String(32), nullable=False, default="complaint", comment="工单类型")
    category: Mapped[Optional[str]] = mapped_column(String(64), default=None, comment="问题分类")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium", comment="urgent/high/medium/low")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", comment="open/processing/resolved/closed")
    content: Mapped[Optional[str]] = mapped_column(Text, default=None, comment="投诉内容，报告快照不保存该原文")
    first_response_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="首次响应时间")
    resolved_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="解决时间")
    satisfaction_score: Mapped[Optional[int]] = mapped_column(Integer, default=None, comment="满意度评分")
    owner_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="处理人 ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_feedback_ticket_status", "status"),
        Index("idx_feedback_ticket_priority", "priority"),
        Index("idx_feedback_ticket_create_time", "create_time"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "学生投诉反馈工单表",
        },
    )


class _LegacyStudentPsychAlert(Base):
    """心理预警最小模型。

    报告只能统计风险等级、状态和跟进时效，不能把学生原文传入快照或 Dify。
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键")
    student_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="学生 ID")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium", comment="low/medium/high")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", comment="pending/following/resolved")
    first_follow_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None, comment="首次跟进时间")
    owner_id: Mapped[Optional[int]] = mapped_column(BIGINT(unsigned=True), default=None, comment="跟进负责人 ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_psych_alert_level", "risk_level"),
        Index("idx_psych_alert_status", "status"),
        Index("idx_psych_alert_create_time", "create_time"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "学生心理预警表",
        },
    )


# 学生模块是两张学生表的唯一 ORM 所有者。保留报告模块的导入名称，避免已有
# 报告代码或外部脚本因导入路径变化中断，但不再向 Base.metadata 注册第二份表。
StudentFeedbackTicket = CanonicalStudentFeedbackTicket
StudentPsychAlert = CanonicalStudentPsychAlert
