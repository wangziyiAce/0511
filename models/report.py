"""
智能报告模块 ORM Model
===========================================
这个文件定义了智能报告模块的两张核心表，实现了从"触发报告生成"到
"AI 生成分析内容"再到"查询报告结果"的完整数据链路。

数据流转过程:
  1. 用户触发报告 → report_generation（status=generating）
  2. 后台聚合业务数据 → 组装 Prompt
  3. 调用 Dify 生成报告 → 保存 report_content + report_html
  4. 更新状态 → status=completed / failed

包含:
  - ReportGeneration  报告生成记录表（P0，核心表）
  - ReportSchedule    报告定时任务表（P1，后续增强）

设计依据:
  《教育服务系统_数据库设计规范文档_V2.1》
  - 第 6.7.1 节  report_generation  报告生成记录表
  - 第 6.9 节    report_schedule    报告定时任务表

核心设计原则:
  1. 🚫 禁用物理外键 — generated_by 字段逻辑关联 sys_user
  2. 🔑 主键统一 — 全部 BIGINT UNSIGNED AUTO_INCREMENT
  3. 📦 JSON 字段 — report_content 用 JSON 存结构化分析结果
  4. 🤖 AI 输出双存储 — report_content(JSON) + report_html(MEDIUMTEXT)
  5. 🔄 异步任务模式 — 提交返回 report_id → 后台生成 → 前端轮询

表间关系速查（逻辑关联，非物理外键）:
  sys_user (1) ──→ (N) report_generation  通过 generated_by 关联
"""

from datetime import datetime, date          # Python 日期时间
from typing import Optional                   # Optional[X] = X | None

# --- SQLAlchemy 通用类型 ---
from sqlalchemy import (
    Date,       # 日期     → MySQL DATE
    DateTime,   # 日期时间 → MySQL DATETIME
    Enum,       # 枚举     → MySQL ENUM
    Index,      # 显式索引
    Integer,    # 整数     → MySQL INT（TINYINT 用 Integer 替代）
    JSON,       # JSON     → MySQL JSON（存储结构化数据）
    String,     # 字符串   → MySQL VARCHAR
    Text,       # 长文本   → MySQL TEXT
    func,       # SQL 函数 → func.now() = MySQL NOW()
)

# --- MySQL 特有类型（支持 UNSIGNED）---
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMTEXT

# --- ORM 声明式映射 ---
from sqlalchemy.orm import Mapped, mapped_column

# --- 导入 ORM 基类 ---
from utils.database import Base


# ============================================================
# 一、ReportGeneration — 报告生成记录表
# ============================================================
# 表序号: 26  |  MVP 优先级: P0（必须创建）
# 表名:   report_generation
# 用途:   记录每次报告生成任务的状态和结果。
#         采用异步任务模式：创建时 status=generating，
#         后台任务完成后更新为 completed 或 failed。
#
# 报告类型枚举:
#   customer_ops     = 全域客户经营分析（数据来源: crm_lead, crm_follow_up）
#   daily_summary    = 员工日报汇总（数据来源: employee_daily_report）
#   psych_weekly     = 学生心理周报（数据来源: student_psych_record, student_psych_alert）
#   complaint_weekly = 投诉处理周报（数据来源: student_feedback_ticket）
#   weekly_summary   = 综合周报（多表聚合）
#
# 报告状态流转:
#   generating → completed（生成成功）
#   generating → failed（生成失败，记录 error_message）
#
# 关联关系:
#   report_generation.generated_by → sys_user.id（逻辑关联）
# ============================================================

class ReportGeneration(Base):
    __tablename__ = "report_generation"

    # ========================================
    # 字段定义
    # ========================================

    # --- 主键 ---
    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    # --- 报告类型 ---
    # ENUM 限制只能从 5 种报告类型中选择，防止脏数据。
    # customer_ops     → 全域客户经营分析
    # daily_summary    → 员工日报汇总
    # weekly_summary   → 综合周报
    # psych_weekly     → 学生心理周报
    # complaint_weekly → 投诉处理周报
    report_type: Mapped[str] = mapped_column(
        Enum(
            "customer_ops",
            "daily_summary",
            "weekly_summary",
            "psych_weekly",
            "complaint_weekly",
            name="report_generation_report_type",
        ),
        nullable=False,
        comment="报告类型",
    )

    # --- 报告标题 ---
    # 人类可读的报告标题，如"2026年7月第1周日报汇总"
    # String(255) 足够存较长的标题
    report_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="报告标题",
    )

    # --- 报告结构化内容（JSON）---
    # AI 生成的结构化分析结果。
    # 示例结构:
    #   {
    #     "summary": "本周整体工作进展顺利...",
    #     "key_findings": ["客户咨询量环比增长15%", "签约转化率8.5%"],
    #     "risks": ["张三客户流失风险较高"],
    #     "suggestions": ["加强高意向客户跟进频率"]
    #   }
    # JSON 类型的好处: 前端可以直接解析展示，Dify 输出格式约束在此字段内。
    report_content: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="报告内容（结构化数据）",
    )

    # --- 报告 HTML 内容 ---
    # Dify 生成的 HTML 格式报告，前端可以直接渲染展示。
    # MEDIUMTEXT 最大 16MB，足够存带样式的完整报告。
    report_html: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT,
        default=None,
        comment="报告 HTML 渲染内容",
    )

    # --- 统计周期起始日期 ---
    # 报告覆盖的数据统计起始日期。
    # 示例: 2026-07-01（周报从周一开始）
    period_start: Mapped[Optional[date]] = mapped_column(
        Date,
        default=None,
        comment="统计周期起始",
    )

    # --- 统计周期截止日期 ---
    # 报告覆盖的数据统计截止日期。
    # 示例: 2026-07-07（周报到周日结束）
    period_end: Mapped[Optional[date]] = mapped_column(
        Date,
        default=None,
        comment="统计周期结束",
    )

    # --- 生成人 ID（逻辑关联 sys_user）---
    # 谁触发了这次报告生成。
    # 可为 NULL（定时任务自动触发时无具体操作人）。
    generated_by: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="生成人 → sys_user（逻辑关联）",
    )

    # --- 生成状态 ---
    # generating = 正在生成中（后台任务执行中）
    # completed  = 生成成功（report_content + report_html 已保存）
    # failed     = 生成失败（error_message 记录原因）
    status: Mapped[str] = mapped_column(
        Enum(
            "generating",
            "completed",
            "failed",
            name="report_generation_status",
        ),
        nullable=False,
        default="generating",
        comment="生成状态",
    )

    # --- 失败原因 ---
    # 当 status = failed 时，记录具体错误原因。
    # 示例: "Dify 调用超时"、"业务数据聚合失败：CRM 表不可达"
    # TEXT 最多 65535 字节，足够存详细错误堆栈。
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        default=None,
        comment="失败原因",
    )

    # --- 创建时间 ---
    # ⚠️ 注意：此表只有 create_time，没有 update_time。
    # 报告一旦生成（completed/failed），内容不再修改。
    # 如需重新生成，创建一条新记录。
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    # ========================================
    # 表级约束
    # ========================================
    __table_args__ = (
        # 按报告类型筛选（如"查看所有日报汇总"）
        Index("idx_report_type", "report_type"),
        # 按统计周期查询（如"7月第1周的所有报告"）
        Index("idx_period", "period_start", "period_end"),
        # 按状态筛选（如"查看所有生成中的报告"）
        Index("idx_status", "status"),
        # 按生成人查询（如"我生成的所有报告"）
        Index("idx_generated_by", "generated_by"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "报告生成记录表",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<ReportGeneration(id={self.id}, report_type={self.report_type!r}, "
            f"status={self.status!r})>"
        )


# ============================================================
# 二、ReportSchedule — 报告定时任务表
# ============================================================
# 表序号: 27  |  MVP 优先级: P1（后续增强）
# 表名:   report_schedule
# 用途:   配置定时报告任务，支持日/周定时自动生成报告。
#
# 使用场景:
#   - 每周一早上 9:00 自动生成上周的日报汇总
#   - 每月 1 号自动生成上月的客户经营分析报告
#   - 自动将生成的报告发送给指定接收人
#
# 注意:
#   - MVP 阶段建表但不实现定时调度逻辑（使用外部 cron 或 Celery 后续增强）
#   - 当前仅作为配置表，为 P2 的定时报告功能预留数据模型
# ============================================================

class ReportSchedule(Base):
    __tablename__ = "report_schedule"

    # ========================================
    # 字段定义
    # ========================================

    # --- 主键 ---
    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    # --- 报告类型 ---
    # 与 report_generation.report_type 对应。
    # 使用 VARCHAR(64) 而非 ENUM，因为后续可能扩展新类型。
    report_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="报告类型",
    )

    # --- Cron 表达式 ---
    # 标准的 5 字段 cron 表达式。
    # 示例:
    #   "0 9 * * 1"    = 每周一早上 9:00
    #   "0 8 1 * *"    = 每月 1 号早上 8:00
    #   "0 18 * * 5"   = 每周五下午 6:00
    cron_expression: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Cron 表达式",
    )

    # --- 接收人列表（JSON）---
    # 报告生成后推送给哪些用户。
    # 示例: [{"user_id": 1, "channel": "email"}, {"user_id": 2, "channel": "system"}]
    recipients: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="接收人列表",
    )

    # --- 启用状态 ---
    # 1 = 启用（定时任务生效）
    # 0 = 禁用（暂停定时生成）
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="1=启用 0=禁用",
    )

    # --- 上次执行时间 ---
    # 记录定时任务最近一次成功执行的时间。
    # 用于判断下次触发时是否需要补跑。
    last_run_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=None,
        comment="上次执行时间",
    )

    # --- 创建时间 ---
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    # --- 更新时间 ---
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    # ========================================
    # 表级约束
    # ========================================
    __table_args__ = (
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "报告定时任务表",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<ReportSchedule(id={self.id}, report_type={self.report_type!r}, "
            f"cron={self.cron_expression!r})>"
        )
