"""
基础设施模块（sys_ 前缀）ORM Model
===========================================
这个文件定义了教育服务系统最核心的三张基础表，所有其他模块
（CRM、学生助手、客服Agent、智能报告）都依赖这些表。

包含:
  - SysRole         系统角色字典表（admin/员工/经理/班主任/学生）
  - SysUser          统一用户表（所有用户在此登录，不区分学生/员工表）
  - SysOrganization  组织架构表（公司部门树形结构）

设计依据:
  《教育服务系统_数据库设计规范文档_V2.1》
  - 第 6.2.1 节  sys_role        系统角色字典表
  - 第 6.2.2 节  sys_user         统一用户表
  - 第 6.9 节    sys_organization 组织架构表

核心设计原则（全文贯彻）:
  1. 🚫 禁用物理外键 — 不用 FOREIGN KEY，改用 {entity}_id + 索引 + 应用层校验
     原因: 物理外键会导致行锁升级、分库分表困难、数据迁移受阻
     详见设计规范文档第 5 章
  2. 🔑 主键统一 — 全部使用 BIGINT UNSIGNED AUTO_INCREMENT
     含义: 无符号大整数（0 ~ 18446744073709551615），自增
     足够支撑亿级数据量
  3. 🕐 时间字段统一 — 每表必有 create_time + update_time
     create_time: 记录创建时自动填入当前时间，之后永不改变
     update_time: 每次 UPDATE 操作自动刷新为当前时间
  4. 💬 中文注释 — 每表和每字段都带 comment，方便 DBA 和后续维护者理解

SQLAlchemy 2.0 编码风格说明:
  使用 Mapped[类型] + mapped_column() 的风格（写起来更接近 Python 类型注解）
  等效于旧风格的 Column(Integer, ...) 但类型检查更友好。
  如果你更习惯旧风格，可以混用，SQLAlchemy 2.0 完全兼容旧写法。

表间关系速查（逻辑关联，非物理外键）:
  sys_role (1) ──→ (N) sys_user       通过 sys_user.role_id 关联
  sys_user (1) ──→ (N) sys_organization 组织内可以有多名用户
  sys_organization (1) ──→ (N) sys_organization  自引用树形结构（parent_id）
"""

from datetime import datetime      # Python 日期时间类型
from typing import Optional        # Optional[X] = X | None（字段可空时用）

# --- SQLAlchemy 通用类型 ---
from sqlalchemy import (
    DateTime,   # 日期时间 → MySQL 的 DATETIME
    Enum,       # 枚举     → MySQL 的 ENUM('a','b','c')
    Index,      # 索引     → 用于在 __table_args__ 中创建显式索引
    Integer,    # 整数     → MySQL 的 INT
    String,     # 字符串   → MySQL 的 VARCHAR(n)
    Text,       # 长文本   → MySQL 的 TEXT（最大 65535 字节）
    func,       # SQL 函数 → func.now() = MySQL 的 NOW()
)

# --- MySQL 特有类型 ---
# BIGINT(unsigned=True) 生成 MySQL 的 BIGINT UNSIGNED
# 不能用 sqlalchemy.BigInteger()，因为标准 SQL 没有 UNSIGNED 概念，
# 必须用 MySQL 方言的类型才能指定 unsigned=True
from sqlalchemy.dialects.mysql import BIGINT

# --- SQLAlchemy ORM 声明式映射 ---
# Mapped[X]     = 类型注解标记，告诉类型检查器这个字段的 Python 类型
# mapped_column = 等价于旧风格的 Column()，定义数据库列的属性
from sqlalchemy.orm import Mapped, mapped_column

# --- 导入 ORM 基类 ---
# 继承 Base 后，SQLAlchemy 会自动将类映射为数据库表
from utils.database import Base


# ============================================================
# 一、SysRole — 系统角色字典表
# ============================================================
# 表序号: 1  |  MVP 优先级: P0（必须建表）
# 表名:   sys_role
# 用途:   定义系统中有哪些角色，每个角色有不同的菜单/接口权限
# 种子数据: admin / employee / manager / team_leader / student（共 5 条）
#
# 关联关系:
#   sys_role.id ← sys_user.role_id（一个角色下有很多用户）
#
# 使用场景:
#   用户登录时，根据其 role_id 查出 role_code，
#   前端根据 role_code 显示/隐藏不同的菜单项。
# ============================================================

class SysRole(Base):
    # --- 表名 ---
    # 数据库中显示为 sys_role，表名不能和 MySQL 保留字冲突
    __tablename__ = "sys_role"

    # ========================================
    # 字段定义
    # ========================================

    # --- 主键 ---
    # BIGINT(unsigned=True) → MySQL: BIGINT UNSIGNED
    #   范围: 0 ~ 2^64 - 1（约 1844 亿亿）
    #   选用 BIGINT 而非 INT 是因为 MVP 后数据量可能很大（虽然角色表很小，但统一风格）
    # primary_key=True      → 主键约束
    # autoincrement=True    → 自增（MySQL 的 AUTO_INCREMENT）
    # comment="主键"        → 写入 MySQL 表的 COMMENT 属性
    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    # --- 角色编码 ---
    # 英文编码，程序内部使用。不允许重复（通过唯一索引 uk_role_code 约束）。
    # 可选值: admin / employee / manager / team_leader / student
    # String(32) → VARCHAR(32)，足够存角色编码
    # nullable=False → 不允许为空
    role_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="角色编码 (admin/employee/manager/team_leader/student)",
    )

    # --- 角色名称 ---
    # 中文显示名，在界面上展示给用户看。
    # String(64) → VARCHAR(64)，如"系统管理员"、"班主任"等
    role_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="角色名称",
    )

    # --- 角色描述 ---
    # 可选的补充说明。比如"最高权限，可管理所有模块"。
    # Optional[str] = str | None → 可以为 None（数据库中的 NULL）
    # default=None → 插入时不传这个字段则默认为 NULL
    description: Mapped[Optional[str]] = mapped_column(
        String(255),
        default=None,
        comment="角色描述",
    )

    # --- 状态 ---
    # 1 = 启用，0 = 禁用
    # 用 TINYINT 存布尔逻辑，比 CHAR(1) 更高效。
    # 为什么不用 ENUM？因为状态只有 0/1 两个值，INT 更简单。
    # default=1 → 新增角色默认启用
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="状态 1=启用 0=禁用",
    )

    # --- 创建时间 ---
    # server_default=func.now() → 在数据库端生成默认值（MySQL 的 NOW()）
    # 为什么不用 Python 端的 default=datetime.now？
    #   server_default 把生成时间的责任交给数据库，即使直接操作 SQL 插入
    # 也能正确记录时间，比 Python 端 default 更可靠。
    # ⚠️ 此字段插入后永不更新。
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    # --- 更新时间 ---
    # onupdate=func.now() → 每次 UPDATE 操作自动刷新为当前时间
    # 同时有 server_default（插入时默认值）和 onupdate（更新时自动刷新）
    # ⚠️ 无需在业务代码中手动设置，SQLAlchemy 自动处理。
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),   # 插入时的默认值
        onupdate=func.now(),          # 更新时自动刷新
        comment="更新时间",
    )

    # ========================================
    # 表级约束（索引 + 存储引擎 + 字符集 + 注释）
    # ========================================
    # __table_args__ 是一个元组，包含:
    #   1. 若干个 Index 对象（索引定义）
    #   2. 一个 dict（表级属性）
    #
    # 索引命名规则:
    #   uk_xxx  = Unique Key（唯一索引）
    #   idx_xxx = 普通索引
    __table_args__ = (
        # uk_role_code: 确保角色编码不重复，同时加速按 role_code 查询
        Index("uk_role_code", "role_code", unique=True),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",                         # 存储引擎（支持事务）
            "mysql_charset": "utf8mb4",                       # 字符集（完整 UTF-8）
            "mysql_collate": "utf8mb4_unicode_ci",            # 排序规则（大小写不敏感）
            "comment": "系统角色字典表",                        # 表注释
        },
    )

    # --- 调试输出 ---
    # 当你在代码中 print(role) 或在断点中查看时，显示对人友好的信息。
    # !r 表示用 repr() 格式输出字符串（带引号，方便看空值和特殊字符）
    def __repr__(self) -> str:
        return f"<SysRole(id={self.id}, role_code={self.role_code!r})>"


# ============================================================
# 二、SysUser — 统一用户表
# ============================================================
# 表序号: 2  |  MVP 优先级: P0（必须建表）
# 表名:   sys_user
# 用途:   系统中所有人的账号信息。不管是学生、员工还是管理员，都在这里登录。
#         通过 user_type 字段区分身份，扩展信息放在各自的子表中。
#
# 设计思路（统一用户表的优势）:
#   传统做法: 建三张表 student / employee / admin，各自有 username/password
#   统一做法: 所有人在 sys_user 中登录，user_type 区分身份
#   优势: 登录逻辑只需写一次，改密码/重置密码/权限校验全部统一处理
#
# 关联关系:
#   sys_user.role_id       → sys_role.id（用户属于哪个角色）
#   sys_user.id            → student_info.user_id（学生的扩展信息 1:1）
#   sys_user.id            → crm_lead.owner_employee_id（员工负责的客户 1:N）
#   sys_user.id            → crm_follow_up.employee_id（员工的跟进记录 1:N）
#   sys_user.id            → event_registration.user_id（用户的报名记录 1:N）
#   sys_user.id            → customer_profile.evaluator_id（研判人的研判结果 1:N）
#
# 密码安全:
#   密码用 bcrypt 哈希存储，成本因子 12（见 config.py）。
#   即使数据库泄露，攻击者也难以反推出明文密码。
#   不要自己写哈希算法，bcrypt 是业界标准。
# ============================================================

class SysUser(Base):
    __tablename__ = "sys_user"

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

    # --- 登录账号 ---
    # 用户登录时输入的用户名。唯一约束（uk_username），全表不允许重复。
    # String(64) 足够存英文用户名或手机号。
    # ⚠️ 这是登录凭证的一部分，不要存明文密码在这里。
    username: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="登录账号",
    )

    # --- 密码哈希 ---
    # 存储的是 bcrypt 哈希值，不是明文密码！
    # 哈希值示例: $2b$12$LJ3m4ys3GZfnYMz8kVsKa.KX9zQb0Fk3...
    # String(255) 足够存 bcrypt 输出（固定 60 字符，多留空间兼容未来算法升级）
    # ⚠️ 永远不要把密码明文存入数据库或日志！
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt 密码哈希",
    )

    # --- 真实姓名 ---
    # 用于界面展示和报告生成，如"张三"。
    # 与 username（登录账号）分离：username 是英文标识，real_name 是中文显示名。
    real_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="真实姓名",
    )

    # --- 用户类型 ---
    # ENUM("student", "employee", "admin")
    # 决定用户的身份，进而决定:
    #   1. 登录后跳转哪个页面（学生端/员工端/管理后台）
    #   2. 哪些 API 接口可以访问
    #   3. 是否在 student_info 表中有对应的扩展记录
    # name="sys_user_user_type" → 给这个 ENUM 类型取名，多个表不能重名
    user_type: Mapped[str] = mapped_column(
        Enum("student", "employee", "admin", name="sys_user_user_type"),
        nullable=False,
        comment="用户类型",
    )

    # --- 角色 ID（逻辑关联 sys_role）---
    # 外键字段命名规则: {关联表名去掉前缀}_id → role_id
    # 允许为 NULL，因为可以先创建用户再分配角色
    # ⚠️ 这只是普通 BIGINT 字段 + 索引，不是 FOREIGN KEY！
    #     数据库层面不会校验 role_id 对应的角色是否真的存在。
    #     应用层需要自己校验（在 Service 层插入前查询 sys_role）。
    role_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="关联角色ID → sys_role（逻辑关联）",
    )

    # --- 所属部门/院系 ---
    # 对员工: 存部门名称（如"咨询部"、"教务部"）
    # 对学生: 存院系名称（如"计算机学院"）
    # 更复杂的组织架构信息在 sys_organization 表中
    department: Mapped[Optional[str]] = mapped_column(
        String(128),
        default=None,
        comment="所属部门/院系",
    )

    # --- 联系方式 ---
    # 存手机号和/或邮箱。格式自由，因为业务上可能只填一种。
    # 用于系统通知、班主任联系学生等场景。
    contact_info: Mapped[Optional[str]] = mapped_column(
        String(128),
        default=None,
        comment="联系方式（手机/邮箱）",
    )

    # --- 头像 URL ---
    # 存储头像文件的访问路径，不是文件本身。
    # 设计规范明确: 文件只存路径不存二进制。
    # 512 字符足够存完整 URL（含参数）。
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        default=None,
        comment="头像URL",
    )

    # --- 账号状态 ---
    # normal   = 正常，可以登录使用
    # disabled = 禁用，无法登录（替代物理删除，保留数据可追溯）
    status: Mapped[str] = mapped_column(
        Enum("normal", "disabled", name="sys_user_status"),
        nullable=False,
        default="normal",
        comment="账号状态",
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
        # uk_username: 确保登录账号唯一，防止重复注册
        Index("uk_username", "username", unique=True),
        # idx_user_type: 加速按类型查询（如"列出所有学生"）
        # SQLAlchemy 会为每个 Index 自动生成 CREATE INDEX ... 语句
        Index("idx_user_type", "user_type"),
        # idx_role_id: 逻辑外键必须建索引（替代物理外键的索引需求）
        # 加速"列出某角色的所有用户"查询
        Index("idx_role_id", "role_id"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "统一用户表",
        },
    )

    def __repr__(self) -> str:
        return f"<SysUser(id={self.id}, username={self.username!r}, user_type={self.user_type!r})>"


# ============================================================
# 三、SysOrganization — 组织架构表
# ============================================================
# 表序号: 3  |  MVP 优先级: P1（建议建表，丰富演示场景）
# 表名:   sys_organization
# 用途:   存储企业组织架构的树形结构（公司 → 部门 → 小组）。
#         通过 parent_id 自引用实现任意层级的树。
#
# 树形结构的实现:
#   parent_id = NULL   → 根节点（如"某某教育集团"）
#   parent_id = 上级ID  → 子节点（如"咨询部"的 parent_id 指向"某某教育集团"）
#
# 查询示例:
#   # 查某部门的所有子部门
#   db.query(SysOrganization).filter_by(parent_id=1).all()
#   # 查某部门的所有员工
#   db.query(SysUser).filter_by(department="咨询部").all()
# ============================================================

class SysOrganization(Base):
    __tablename__ = "sys_organization"

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

    # --- 组织名称 ---
    # 如"某某教育集团"、"咨询部"、"一组"
    org_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="组织名称",
    )

    # --- 上级组织 ID（自引用逻辑关联）---
    # 指向自己的父节点。整个树形结构就是靠这个字段实现的。
    # NULL = 顶层节点（根组织）。
    # ⚠️ 这是逻辑关联，不是物理外键。应用层需自行校验父节点是否存在。
    parent_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(unsigned=True),
        default=None,
        comment="上级组织ID（逻辑关联）",
    )

    # --- 组织类型 ---
    # 可选值示例: company / department / team / branch
    # String(32) 而非 ENUM，因为组织类型可能随业务发展而变化
    org_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        default=None,
        comment="组织类型",
    )

    # --- 排序权重 ---
    # 在同级节点中按此值从小到大排列。
    # default=0 表示默认排在最前面。
    # 前端展示组织树时: ORDER BY sort_order ASC, id ASC
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="排序",
    )

    # --- 状态 ---
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
        # idx_parent_id: 加速"查某节点的所有子节点"
        # 这是自引用树最常见的查询，必须建索引
        Index("idx_parent_id", "parent_id"),
        # --- MySQL 表属性 ---
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "组织架构表",
        },
    )

    def __repr__(self) -> str:
        return f"<SysOrganization(id={self.id}, org_name={self.org_name!r})>"
