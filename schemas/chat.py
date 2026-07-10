"""客服 Agent Pydantic Schema 汇总：课程、活动、会话与消息。"""
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from schemas.common import PaginationParams


class CourseQuery(PaginationParams):
    """课程列表查询参数，Router 将 Query 参数收敛成该对象后交给 Service。"""

    category: Optional[str] = Field(default=None, description="课程分类")
    keyword: Optional[str] = Field(default=None, description="关键词搜索")
    min_price: Optional[Decimal] = Field(default=None, description="最低价格")
    max_price: Optional[Decimal] = Field(default=None, description="最高价格")
    status: Optional[int] = Field(default=1, description="1=上架 0=下架")


class CourseResponse(BaseModel):
    """课程响应，字段名与 course_project 表保持一致。"""

    id: int
    project_name: str
    category: Optional[str] = None
    description: Optional[str] = None
    target_audience: Optional[str] = None
    price: Optional[Decimal] = None
    duration: Optional[str] = None
    tags: Optional[List[str]] = None
    status: int
    create_time: datetime
    update_time: Optional[datetime] = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value):
        """兼容 MySQL JSON 返回数组与 SQLite 测试库返回 JSON 字符串两种形态。"""
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            return parsed if isinstance(parsed, list) else [parsed]
        return value

    model_config = {"from_attributes": True}


class EventQuery(PaginationParams):
    """活动列表查询参数，默认 status=upcoming，服务 Dify 活动查询场景。"""

    status: Optional[str] = Field(default="upcoming", description="upcoming/ongoing/ended/cancelled")
    event_type: Optional[str] = Field(default=None, description="online/offline/hybrid")
    start_date: Optional[str] = Field(default=None, description="开始日期")
    end_date: Optional[str] = Field(default=None, description="结束日期")


class EventResponse(BaseModel):
    """活动响应，直接暴露 event_lecture 表中的业务字段。"""

    id: int
    event_name: str
    event_type: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    current_participants: int
    organizer_id: Optional[int] = None
    status: str
    create_time: datetime

    model_config = {"from_attributes": True}


class EventRegistrationCreate(BaseModel):
    """活动报名请求，支持注册用户 user_id 或访客姓名/联系方式。"""

    user_id: Optional[int] = Field(default=None, description="用户ID（登录用户）")
    customer_name: Optional[str] = Field(default=None, description="客户姓名（未注册用户）")
    contact_info: Optional[str] = Field(default=None, description="联系方式")
    remark: Optional[str] = Field(default=None, description="备注")


class EventRegistrationResponse(BaseModel):
    """活动报名响应，预留给 Router/Swagger 复用。"""

    id: int
    event_id: int
    event_name: Optional[str] = None
    user_id: Optional[int] = None
    customer_name: Optional[str] = None
    contact_info: Optional[str] = None
    status: str
    create_time: datetime

    model_config = {"from_attributes": True}


class ChatSessionCreate(BaseModel):
    """创建/获取会话请求，user_id 存在时可复用已有活跃会话。"""

    user_id: Optional[int] = Field(default=None, description="用户ID")
    visitor_name: Optional[str] = Field(default=None, description="访客昵称")
    visitor_contact: Optional[str] = Field(default=None, description="访客联系方式")


class ChatSessionResponse(BaseModel):
    """会话响应，对齐 chat_session 表字段。"""

    id: int
    session_id: str
    user_id: Optional[int] = None
    visitor_name: Optional[str] = None
    visitor_contact: Optional[str] = None
    status: str
    last_message_time: Optional[datetime] = None
    create_time: datetime
    close_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    """保存消息请求，在 API 层先限制 role 和 content，避免脏数据进入消息表。"""

    role: Literal["user", "assistant", "system"] = Field(..., description="消息角色: user/assistant/system")
    content: str = Field(..., min_length=1, description="消息内容")
    intent: Optional[str] = Field(default=None, description="AI 识别的意图")
    tokens_used: Optional[int] = Field(default=None, description="消耗 Token 数")
    response_time_ms: Optional[int] = Field(default=None, description="响应耗时（毫秒）")


class ChatMessageResponse(BaseModel):
    """消息响应，对齐 chat_message 表字段。"""

    id: int
    session_id: str
    role: str
    content: str
    intent: Optional[str] = None
    tokens_used: Optional[int] = None
    response_time_ms: Optional[int] = None
    create_time: datetime

    model_config = {"from_attributes": True}
