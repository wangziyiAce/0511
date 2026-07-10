"""客服 Agent Service 汇总：课程、活动、报名、会话与消息业务逻辑。"""
import uuid
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from models.chat import (
    ChatMessage,
    ChatSession,
    CourseProject,
    EventLecture,
    EventRegistration,
)
from models.user import SysUser
from schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    CourseQuery,
    EventQuery,
    EventRegistrationCreate,
)
from utils.exceptions import (
    ConflictError,
    NotFoundError,
    ReferenceNotFoundError,
    StateError,
)


def query_courses(db: Session, params: CourseQuery):
    """查询课程列表，支持分类、关键词、价格区间与状态筛选。"""
    query = db.query(CourseProject)

    # 客服 Agent 默认只展示上架课程；后台或调试可显式传 status=0 查看下架数据。
    query = query.filter(CourseProject.status == (params.status if params.status is not None else 1))

    # 只追加调用方实际传入的筛选条件，避免空参数影响默认列表。
    if params.category:
        query = query.filter(CourseProject.category == params.category)
    if params.keyword:
        query = query.filter(CourseProject.project_name.like(f"%{params.keyword}%"))
    if params.min_price is not None:
        query = query.filter(CourseProject.price >= params.min_price)
    if params.max_price is not None:
        query = query.filter(CourseProject.price <= params.max_price)

    total = query.count()
    items = query.order_by(CourseProject.create_time.desc()) \
        .offset(params.offset).limit(params.limit).all()
    return items, total


def get_course_by_id(db: Session, course_id: int) -> Optional[CourseProject]:
    """按主键查询课程详情。"""
    return db.query(CourseProject).filter(CourseProject.id == course_id).first()


def query_events(db: Session, params: EventQuery):
    """查询活动列表，支持状态、类型、日期范围与分页筛选。"""
    query = db.query(EventLecture)

    # 客服 Agent 默认只推荐待开始活动，避免把已结束或已取消活动推给用户。
    if params.status:
        query = query.filter(EventLecture.status == params.status)
    else:
        query = query.filter(EventLecture.status == "upcoming")
    if params.event_type:
        query = query.filter(EventLecture.event_type == params.event_type)
    if params.start_date:
        query = query.filter(EventLecture.start_time >= params.start_date)
    if params.end_date:
        query = query.filter(EventLecture.start_time <= params.end_date)

    total = query.count()
    items = query.order_by(EventLecture.start_time.asc()) \
        .offset(params.offset).limit(params.limit).all()
    return items, total


def get_event_by_id(db: Session, event_id: int) -> Optional[EventLecture]:
    """按主键查询活动详情。"""
    return db.query(EventLecture).filter(EventLecture.id == event_id).first()


def register_for_event(
    db: Session,
    event_id: int,
    data: EventRegistrationCreate,
):
    """活动报名：在同一事务中完成业务校验、创建报名记录与名额递增。"""
    # Router 负责 commit/rollback；Service 只在当前事务中完成业务步骤。
    # MySQL 下 with_for_update() 会生成 SELECT ... FOR UPDATE，锁住活动行防止并发超额。
    event = db.query(EventLecture).filter(
        EventLecture.id == event_id
    ).with_for_update().first()

    if not event:
        raise NotFoundError("活动不存在")

    if event.status != "upcoming":
        raise StateError("活动状态不允许报名")

    # 名额校验必须在行锁内完成，否则并发报名可能出现超卖。
    if event.current_participants >= (event.max_participants or 999999):
        raise StateError("活动名额已满")

    # 已取消记录不阻止重新报名；未取消记录视为重复报名。
    if data.user_id:
        existing = db.query(EventRegistration).filter(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == data.user_id,
            EventRegistration.status != "cancelled",
        ).first()
        if existing:
            raise ConflictError("该用户已报名此活动")

    if data.contact_info:
        existing = db.query(EventRegistration).filter(
            EventRegistration.event_id == event_id,
            EventRegistration.contact_info == data.contact_info,
            EventRegistration.status != "cancelled",
        ).first()
        if existing:
            raise ConflictError("该联系方式已报名此活动")

    # 数据库无物理外键，user_id 存在性必须在应用层校验。
    if data.user_id:
        user_exists = db.query(
            db.query(SysUser).filter(SysUser.id == data.user_id).exists()
        ).scalar()
        if not user_exists:
            raise ReferenceNotFoundError("用户", data.user_id)

    registration = EventRegistration(
        event_id=event_id,
        user_id=data.user_id,
        customer_name=data.customer_name,
        contact_info=data.contact_info,
        status="registered",
        remark=data.remark,
    )
    db.add(registration)

    # 使用表达式递增，避免基于旧对象值覆盖并发更新结果。
    db.execute(
        update(EventLecture)
        .where(EventLecture.id == event_id)
        .values(current_participants=EventLecture.current_participants + 1)
    )
    db.flush()

    return registration


def cancel_registration(db: Session, event_id: int, user_id: int):
    """取消活动报名，并在同一事务中回退活动当前报名人数。"""
    # 取消报名同样锁定活动和报名记录，防止与并发报名/取消同时修改人数。
    event = db.query(EventLecture).filter(
        EventLecture.id == event_id
    ).with_for_update().first()
    if not event:
        raise NotFoundError("活动不存在")

    registration = db.query(EventRegistration).filter(
        EventRegistration.event_id == event_id,
        EventRegistration.user_id == user_id,
        EventRegistration.status == "registered",
    ).with_for_update().first()

    if not registration:
        raise NotFoundError("报名记录不存在或已取消")

    registration.status = "cancelled"

    # 防御性保护计数不为负；正常路径下每次取消只会减少一个有效报名。
    event.current_participants = max((event.current_participants or 0) - 1, 0)
    db.flush()

    return registration


def create_or_get_session(db: Session, data: ChatSessionCreate) -> ChatSession:
    """创建新会话；已登录用户存在活跃会话时直接复用。"""
    # 登录用户复用活跃会话，避免同一用户在 Dify 多轮对话中产生多条会话。
    if data.user_id:
        existing = db.query(ChatSession).filter(
            ChatSession.user_id == data.user_id,
            ChatSession.status == "active",
        ).first()
        if existing:
            return existing

    # 访客或没有活跃会话的用户创建新会话，cs_ 前缀便于日志检索。
    session_id = f"cs_{uuid.uuid4().hex[:16]}"
    session = ChatSession(
        session_id=session_id,
        user_id=data.user_id,
        visitor_name=data.visitor_name,
        visitor_contact=data.visitor_contact,
        status="active",
    )
    db.add(session)
    return session


def get_session_by_id(db: Session, session_id: str) -> Optional[ChatSession]:
    """按 session_id 查询客服会话。"""
    return db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()


def save_message(
    db: Session,
    session_id: str,
    data: ChatMessageCreate,
) -> ChatMessage:
    """保存会话消息，并更新会话最后消息时间。"""
    # chat_message 只保存已有会话的消息；无物理外键时由应用层做逻辑校验。
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()
    if not session:
        raise NotFoundError("会话不存在")

    message = ChatMessage(
        session_id=session_id,
        role=data.role,
        content=data.content,
        intent=data.intent,
        tokens_used=data.tokens_used,
        response_time_ms=data.response_time_ms,
    )
    db.add(message)

    # last_message_time 作为会话列表排序和超时判断依据。
    session.last_message_time = func.now()

    return message


def get_session_messages(
    db: Session,
    session_id: str,
    cursor: Optional[int] = None,
    limit: int = 20,
):
    """按游标分页获取会话消息，最新消息排在前面。"""
    query = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.id.desc())

    if cursor:
        query = query.filter(ChatMessage.id < cursor)

    # 多取 1 条判断是否还有下一页，返回时只截取 limit 条。
    messages = query.limit(limit + 1).all()
    has_more = len(messages) > limit
    items = messages[:limit]
    next_cursor = items[-1].id if items else None

    return items, next_cursor, has_more
