"""客服 Agent ORM 模型汇总：课程、活动、报名、会话与消息。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    DECIMAL,
    Enum,
    Integer,
    JSON,
    String,
    Text,
    func,
)

from models.common import BigIntPrimaryKey, TimestampMixin
from utils.database import Base


class CourseProject(Base, TimestampMixin):
    """课程/项目表，对应 API 文档中的 course_project 数据源。"""

    __tablename__ = "course_project"

    # 字段名保持与数据库设计文档一致，响应层不做 name/title 等二次翻译。
    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    project_name = Column(String(255), nullable=False, comment="项目/课程名称")
    category = Column(String(64), default=None, comment="类别（语言培训/背景提升/硕博连读）")
    description = Column(Text, default=None, comment="项目详情介绍")
    target_audience = Column(String(255), default=None, comment="适合人群/学历要求")
    price = Column(DECIMAL(10, 2), default=None, comment="价格")
    duration = Column(String(64), default=None, comment="课程周期")
    tags = Column(JSON, default=None, comment="标签（用于匹配推荐）")
    status = Column(Integer, nullable=False, default=1, comment="1=上架 0=下架")


class EventLecture(Base, TimestampMixin):
    """活动/讲座主表，报名人数 current_participants 由应用层维护。"""

    __tablename__ = "event_lecture"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    event_name = Column(String(255), nullable=False, comment="活动/讲座名称")
    event_type = Column(
        Enum("online", "offline", "hybrid", name="event_type_enum"),
        nullable=False,
        comment="类型",
    )
    description = Column(Text, default=None, comment="活动详情")
    start_time = Column(DateTime, nullable=False, comment="开始时间")
    end_time = Column(DateTime, default=None, comment="结束时间")
    location = Column(String(255), default=None, comment="地点或线上链接")
    max_participants = Column(Integer, default=None, comment="最大报名人数")
    current_participants = Column(Integer, nullable=False, default=0, comment="当前报名人数（应用层维护）")
    organizer_id = Column(BigInteger, default=None, comment="组织者 -> sys_user（逻辑关联）")
    status = Column(
        Enum("upcoming", "ongoing", "ended", "cancelled", name="event_status_enum"),
        nullable=False,
        default="upcoming",
        comment="活动状态",
    )

    def __init__(self, **kwargs):
        # 业务代码应传 datetime；这里兼容测试与脚本中常见的字符串时间写法。
        for field in ("start_time", "end_time"):
            value = kwargs.get(field)
            if isinstance(value, str):
                kwargs[field] = datetime.fromisoformat(value.replace(" ", "T"))
        super().__init__(**kwargs)


class EventRegistration(Base):
    """活动报名表，无物理外键，event_id/user_id 由 Service 层做逻辑校验。"""

    __tablename__ = "event_registration"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    event_id = Column(BigInteger, nullable=False, comment="-> event_lecture.id（逻辑关联）")
    user_id = Column(BigInteger, default=None, comment="报名用户 -> sys_user（逻辑关联）")
    customer_name = Column(String(64), default=None, comment="报名客户姓名（未注册用户）")
    contact_info = Column(String(128), default=None, comment="联系方式")
    status = Column(
        Enum("registered", "attended", "cancelled", "no_show", name="reg_status_enum"),
        nullable=False,
        default="registered",
        comment="报名状态",
    )
    remark = Column(String(255), default=None, comment="备注")
    create_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")


class ChatSession(Base):
    """客服会话表，session_id 面向 Dify/前端传递，id 仅作内部主键。"""

    __tablename__ = "chat_session"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    session_id = Column(String(64), nullable=False, comment="会话唯一标识")
    user_id = Column(BigInteger, default=None, comment="关联用户 -> sys_user（逻辑关联）")
    visitor_name = Column(String(64), default=None, comment="访客昵称")
    visitor_contact = Column(String(128), default=None, comment="访客联系方式（用于线索收集）")
    status = Column(
        Enum("active", "closed", "timeout", name="session_status_enum"),
        nullable=False,
        default="active",
        comment="会话状态",
    )
    last_message_time = Column(DateTime, default=None, comment="最后消息时间")
    create_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    close_time = Column(DateTime, default=None, comment="会话关闭时间")


class ChatMessage(Base):
    """客服消息表，按 session_id 与 chat_session 做逻辑关联。"""

    __tablename__ = "chat_message"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    session_id = Column(String(64), nullable=False, comment="-> chat_session.session_id（逻辑关联）")
    role = Column(
        Enum("user", "assistant", "system", name="msg_role_enum"),
        nullable=False,
        comment="消息角色",
    )
    content = Column(Text, nullable=False, comment="消息内容")
    intent = Column(String(64), default=None, comment="AI 识别的意图")
    tokens_used = Column(Integer, default=None, comment="本次消耗 Token 数")
    response_time_ms = Column(Integer, default=None, comment="响应耗时（毫秒）")
    create_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
