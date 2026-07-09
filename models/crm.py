"""
客户研判模块 ORM Model
===========================================
这个文件定义了客户画像研判的三张核心表，实现了从"客户信息输入"到
"AI 智能匹配产品"的完整数据链路。

数据流转过程:
  1. 客户信息进入 → customer_source（记录来源 + AI 解析）
  2. 规则配置     → profile_rule（定义匹配规则 + AI 提示词）
  3. AI 研判结果  → customer_profile（输出匹配哪个产品 + 评分）

包含:
  - ProfileRule      画像研判规则表（配置怎么匹配客户到产品线）
  - CustomerSource   客户信息来源记录表（客户资料从哪来、解析状态）
  - CustomerProfile  客户画像研判结果表（AI 研判后的匹配结果）

设计依据:
  《教育服务系统_数据库设计规范文档_V2.1》
  - 第 6.3.1 节  profile_rule     画像研判规则表
  - 第 6.3.2 节  customer_source   客户信息来源记录表
  - 第 6.3.3 节  customer_profile  客户画像研判结果表

核心设计原则:
  1. 🚫 禁用物理外键 — 关联字段 source_id / operator_id / evaluator_id 均为逻辑关联
  2. 🔑 主键统一 — 全部 BIGINT UNSIGNED AUTO_INCREMENT
  3. 📦 JSON 字段 — 结构化数据（规则配置、解析结果、推荐列表）用 JSON 类型
  4. 🤖 AI 输出双存储 — 保存原始文本（match_reason） + 结构化 JSON（background_info）

业务背景:
  教育服务机构的客户来自多种渠道（线上表单、简历文件、线下咨询等）。
  客户研判模块的核心功能是:
    输入: 客户的基本信息（学历、年龄、意向国家...）
    处理: AI 根据研判规则匹配合适的产品线
    输出: 匹配结果 + 推荐项目列表 + 评分 + 理由

表间关系速查（逻辑关联，非物理外键）:
  customer_source  (1) ──→ (1) customer_profile  通过 source_id 关联
  sys_user         (1) ──→ (N) customer_source    通过 operator_id 关联
  sys_user         (1) ──→ (N) customer_profile   通过 evaluator_id 关联
"""

from datetime import datetime      # Python 日期时间
from decimal import Decimal        # Python 精确小数（用于金额/评分）
from typing import Optional        # Optional[X] = X | None

# --- SQLAlchemy 通用类型 ---
from sqlalchemy import (
    DateTime,   # 日期时间 → MySQL DATETIME
    Enum,       # 枚举     → MySQL ENUM
    Index,      # 显式索引
    Integer,    # 整数     → MySQL INT
    JSON,       # JSON     → MySQL JSON（存储结构化数据）
    Numeric,    # 定点数   → MySQL DECIMAL（精确到指定小数位）
    String,     # 字符串   → MySQL VARCHAR
    Text,       # 长文本   → MySQL TEXT
    func,       # SQL 函数 → func.now() = MySQL NOW()
)

# --- MySQL 特有类型（支持 UNSIGNED）---
from sqlalchemy.dialects.mysql import BIGINT

# --- ORM 声明式映射 ---
from sqlalchemy.orm import Mapped, mapped_column

# --- 导入 ORM 基类 ---
from utils.database import Base


# ============================================================
# 一、ProfileRule — 画像研判规则表
# ============================================================
# 表序号: 4  |  MVP 优先级: P1（建议建表）
# 表名:   profile_rule
# 用途:   定义 AI 用什么规则把客户匹配到产品线。
#         每条规则关联一个产品线，配置了匹配条件和 AI 提示词。
#
# 场景举例:
#   产品线"硕博连读"的课程面向本科毕业生，
#   研判规则: 学历=本科 + 年龄<28 + 有研究经历 → 匹配该产品线
#   rule_content 存这个规则的 JSON 配置，
#   match_prompt 存发给 AI 的系统提示词。
#
# 关联关系:
#   本表无逻辑外键，独立配置，被 customer_profile 的研判逻辑引用。
#
# 使用场景:
#   运营人员在后台配置规则 → Dify 工作流读取规则 + 客户信息 → 调用 AI 研判
# ============================================================

class ProfileRule(Base):
    __tablename__ = "profile_rule"

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

    # --- 产品线 ---
    # 这条规则适用于哪个产品线。
    # 示例值: "留学申请"、"背景提升"、"硕博连读"
    # 通过 idx_product_line 索引加速按产品线筛选规则。
    # ⚠️ 这里存的是业务标识，需要与 course_project.category 等字段对应。
    product_line: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="产品线（留学申请/背景提升/硕博连读）",
    )

    # --- 规则名称 ---
    # 人类可读的名字，如"硕博连读-本科毕业生匹配规则"
    # String(128) 够长，可以写比较详细的名称
    rule_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="规则名称",
    )

    # --- 规则配置（JSON）---
    # 这是规则的核心内容，以结构化 JSON 存储。
    # 示例结构:
    #   {
    #     "conditions": {
    #       "education": ["本科", "硕士"],
    #       "age_range": [22, 35],
    #       "language_score": {"ielts": 6.0, "toefl": 80},
    #       "intended_countries": ["美国", "英国", "加拿大"]
    #     },
    #     "weight": {
    #       "education": 0.3,
    #       "language": 0.3,
    #       "research": 0.2,
    #       "gpa": 0.2
    #     }
    #   }
    # JSON 类型的好处: 可以灵活增减条件字段，不需要改表结构。
    # ⚠️ JSON 字段不能建普通索引，高频率查询时考虑生成列 + 虚拟索引
    #   （见设计规范第 3.5 节）
    rule_content: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="研判规则配置（学历/语言/年龄等条件）",
    )

    # --- AI 研判系统提示词 ---
    # 调用 Dify / LLM 时作为 system prompt 使用。
    # 可选字段，不填则用默认提示词。
    # 示例: "你是一个留学顾问，请根据以下客户背景，判断最适合的产品线..."
    match_prompt: Mapped[Optional[str]] = mapped_column(
        Text,           # TEXT 类型 → 最大 65535 字节，足够存长提示词
        default=None,
        comment="AI 研判使用的系统提示词",
    )

    # --- 优先级 ---
    # 多条规则可能同时匹配一个客户，优先级高的规则先执行。
    # 数值越大越优先。
    # 默认 0 = 最低优先级。
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="优先级（数值越大越优先）",
    )

    # --- 状态 ---
    # 1=启用（规则生效），0=禁用（规则暂时停用）
    # 禁用比删除好，因为可以随时恢复，且保留历史配置记录。
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="1=启用 0=禁用",
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
        # idx_product_line: 加速"查某产品线的所有规则"
        Index("idx_product_line", "product_line"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "画像研判规则表",
        },
    )

    def __repr__(self) -> str:
        return f"<ProfileRule(id={self.id}, product_line={self.product_line!r}, rule_name={self.rule_name!r})>"


# ============================================================
# 二、CustomerSource — 客户信息来源记录表
# ============================================================
# 表序号: 5  |  MVP 优先级: P1（建议建表）
# 表名:   customer_source
# 用途:   记录每条客户信息的来源和 AI 解析状态。
#         支持多种输入方式: 手动录入、文件上传、Excel 批量导入等。
#
# 数据流:
#   1. 用户上传文件或手动录入 → source_type + raw_content / file_url
#   2. AI 解析客户信息       → parse_status 从 pending → success
#   3. 解析结果存入          → parse_result（结构化 JSON）
#   4. 解析失败记录原因      → parse_status = failed + parse_error
#
# ⚠️ 此表没有 update_time 字段（按设计文档 DDL），
#    因为信息来源一旦创建就不需要修改，只需更新解析状态。
#    如需追踪状态变更历史，可通过 parse_status + create_time 判断。
#
# 关联关系:
#   customer_source.id          → customer_profile.source_id（1:1 逻辑关联）
#   customer_source.operator_id → sys_user.id（操作人，逻辑关联）
# ============================================================

class CustomerSource(Base):
    __tablename__ = "customer_source"

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

    # --- 来源类型 ---
    # ENUM 限制只能从这 5 种中选择，防止脏数据。
    #   text       = 纯文本输入（如微信聊天记录粘贴）
    #   pdf_resume = 上传的 PDF 简历文件
    #   excel      = Excel 批量导入
    #   import     = 从其他系统导入
    #   manual     = 人工手动录入
    source_type: Mapped[str] = mapped_column(
        Enum(
            "text",
            "pdf_resume",
            "excel",
            "import",
            "manual",
            name="customer_source_source_type",   # ENUM 类型名称，全局唯一
        ),
        nullable=False,
        comment="来源类型",
    )

    # --- 原始文本内容 ---
    # 当 source_type 为 text 或 manual 时，客户的原始信息存这里。
    # TEXT 最大 65535 字节 ≈ 2 万个中文字，足够存详细描述。
    raw_content: Mapped[Optional[str]] = mapped_column(
        Text,
        default=None,
        comment="原始文本内容",
    )

    # --- 上传文件 URL ---
    # 当 source_type 为 pdf_resume 或 excel 时，文件存储路径。
    # 不存文件二进制数据，只存路径。
    # 示例: "/uploads/2026/07/resume_zhangsan.pdf"
    file_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        default=None,
        comment="上传文件URL",
    )

    # --- 原始文件名 ---
    # 保留用户上传时的文件名，方便追溯。
    # 示例: "张三简历.pdf"
    file_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        default=None,
        comment="原始文件名",
    )

    # --- AI 解析状态 ---
    #   pending = 等待解析（刚上传/录入，还未调用 AI）
    #   success = 解析成功（AI 成功提取了结构化信息）
    #   failed  = 解析失败（AI 无法识别或文件损坏）
    # 系统可以使用这个字段做异步处理：定时任务扫描 pending 记录，逐条调用 AI 解析。
    parse_status: Mapped[str] = mapped_column(
        Enum("pending", "success", "failed", name="customer_source_parse_status"),
        nullable=False,
        default="pending",    # 新建记录默认等待解析
        comment="解析状态",
    )

    # --- AI 解析结果（JSON）---
    # 解析成功后存储的结构化客户信息。
    # 示例结构:
    #   {
    #     "name": "张三",
    #     "age": 24,
    #     "education": "本科",
    #     "school": "北京大学",
    #     "major": "计算机科学",
    #     "language": {"ielts": 7.0},
    #     "intended_country": "美国",
    #     "intended_major": "计算机科学"
    #   }
    parse_result: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="AI 解析后的结构化结果",
    )

    # --- 解析失败原因 ---
    # 当 parse_status = failed 时，记录具体原因。
    # 示例: "文件格式不支持"、"PDF 内容为图片无法提取文字"、"AI 服务超时"
    parse_error: Mapped[Optional[str]] = mapped_column(
        Text,
        default=None,
        comment="解析失败原因",
    )

    # --- 操作人 ID（逻辑关联 sys_user）---
    # 谁上传/录入了这条客户信息。
    # 用于统计和数据追溯。
    operator_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="操作人ID → sys_user（逻辑关联）",
    )

    # --- 创建时间 ---
    # ⚠️ 注意：此表只有 create_time，没有 update_time。
    # 客户来源记录一旦创建，核心信息不再修改。
    # 解析状态的变化通过 parse_status 字段跟踪。
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
        # 按来源类型筛选（如"列出所有 PDF 简历"）
        Index("idx_source_type", "source_type"),
        # 异步任务扫描 pending 状态的记录（最高频查询之一）
        Index("idx_parse_status", "parse_status"),
        # 按操作人查询（如"看我录入的所有客户"）
        Index("idx_operator_id", "operator_id"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "客户信息来源记录表",
        },
    )

    def __repr__(self) -> str:
        return f"<CustomerSource(id={self.id}, source_type={self.source_type!r}, parse_status={self.parse_status!r})>"


# ============================================================
# 三、CustomerProfile — 客户画像研判结果表
# ============================================================
# 表序号: 6  |  MVP 优先级: P1（建议建表）
# 表名:   customer_profile
# 用途:   存储 AI 对客户进行画像研判后的匹配结果。
#         这是客户研判流程的最终产出，回答"这位客户最适合哪个产品线"。
#
# 研判流程:
#   1. 从 customer_source 获取客户基本信息
#   2. 加载 profile_rule 中的匹配规则和提示词
#   3. 调用 Dify AI 进行研判
#   4. 研判结果写入 customer_profile
#
# 匹配结果枚举:
#   matched     = 匹配成功，找到了合适的产品线
#   partial     = 部分匹配，客户条件不完全满足但有潜力
#   not_matched = 未匹配，当前没有适合的产品线（可能是线索质量低或产品线不足）
#
# 关联关系:
#   customer_profile.source_id    → customer_source.id（来源记录 1:1）
#   customer_profile.evaluator_id → sys_user.id（研判人，逻辑关联）
# ============================================================

class CustomerProfile(Base):
    __tablename__ = "customer_profile"

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

    # --- 客户姓名 ---
    # 从 customer_source.parse_result 中提取或手动填入。
    # 可为 NULL，因为解析失败时可能没有姓名。
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        default=None,
        comment="客户姓名",
    )

    # --- 联系方式 ---
    # 手机号或邮箱，用于后续跟进联系。
    # String(128) 足够存手机号(11) + 邮箱(最长254但一般<100)
    contact_info: Mapped[Optional[str]] = mapped_column(
        String(128),
        default=None,
        comment="联系方式",
    )

    # --- 来源 ID（逻辑关联 customer_source）---
    # 指向原始客户信息来源。通过这个字段可以追溯:
    #   - 客户资料是什么时候、通过什么方式进来的
    #   - 原始文件/文本是什么
    #   - 谁录入的
    source_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="→ customer_source.id（逻辑关联）",
    )

    # --- 客户背景信息（JSON）---
    # 结构化存储客户的学历、年龄、语言成绩、意向国家等信息。
    # 示例:
    #   {
    #     "education": "本科",
    #     "age": 24,
    #     "school": "北京大学",
    #     "language_score": {"ielts": 7.0, "toefl": 100},
    #     "intended_country": "美国",
    #     "intended_major": "计算机科学"
    #   }
    # 这些信息是 AI 研判的输入参数。
    background_info: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="客户背景信息（学历/年龄/意向国家）",
    )

    # --- 匹配结果 ---
    # AI 研判的核心结论:
    #   matched     = 成功匹配到合适的产品线 → 可以推进销售流程
    #   partial     = 部分匹配 → 需要人工进一步评估
    #   not_matched = 未匹配 → 可能归档或推荐其他渠道
    match_result: Mapped[Optional[str]] = mapped_column(
        Enum(
            "matched",
            "partial",
            "not_matched",
            name="customer_profile_match_result",    # ENUM 类型名称
        ),
        default=None,
        comment="匹配结果",
    )

    # --- 匹配的产品线 ---
    # 当 match_result = matched 时，记录匹配到的产品线名称。
    # 示例: "硕博连读"、"背景提升-科研项目"
    # 通常与 profile_rule.product_line 对应。
    matched_product: Mapped[Optional[str]] = mapped_column(
        String(128),
        default=None,
        comment="匹配的产品线",
    )

    # --- 匹配度评分 ---
    # 0 ~ 100 的分数，表示客户与该产品线的匹配程度。
    # DECIMAL(5,2) → 最大 999.99，精确到小数点后 2 位。
    # 示例: 85.50 表示 85.5% 匹配度。
    # 评分越高，客户转化可能性越大，销售团队可以优先跟进高分客户。
    match_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),          # 总共 5 位数字，其中 2 位小数
        default=None,
        comment="匹配度评分（0-100）",
    )

    # --- AI 研判原因 ---
    # 记录 AI 给出的匹配/不匹配理由，帮助人工判断 AI 结论是否可信。
    # 示例: "客户本科为计算机专业，有研究经历，语言成绩达标，高度匹配硕博连读项目。"
    # TEXT 类型，最大 65535 字节。
    match_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        default=None,
        comment="AI 研判原因",
    )

    # --- 推荐的专业/项目列表（JSON）---
    # AI 根据客户背景推荐的具体项目列表。
    # 示例:
    #   [
    #     {"name": "MIT计算机硕士", "score": 92, "reason": "专业方向高度匹配"},
    #     {"name": "Stanford CS硕士", "score": 85, "reason": "语言成绩达标"}
    #   ]
    recommended_programs: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        comment="推荐的专业/项目列表",
    )

    # --- 研判人 ID（逻辑关联 sys_user）---
    # 谁触发了这次研判（可能是系统自动，也可能是人工手动研判）。
    # 可为 NULL，因为定时任务/自动触发时没有具体的操作人。
    evaluator_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="研判人 → sys_user（逻辑关联）",
    )

    # --- 创建时间 ---
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    # --- 更新时间 ---
    # 当重新研判或人工修正匹配结果时会自动刷新。
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
        # 追溯客户的原始信息来源
        Index("idx_source_id", "source_id"),
        # 按匹配结果筛选（如"列出所有成功匹配的客户"）
        Index("idx_match_result", "match_result"),
        # 按产品线查看匹配情况（如"硕博连读产品线匹配了多少客户"）
        Index("idx_matched_product", "matched_product"),
        # 按研判人统计工作量
        Index("idx_evaluator_id", "evaluator_id"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "客户画像研判结果表",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<CustomerProfile(id={self.id}, customer_name={self.customer_name!r}, "
            f"match_result={self.match_result!r})>"
        )
