"""客服 Agent 路由汇总：课程、活动、报名、会话与消息。"""
from decimal import Decimal
from threading import RLock
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    CourseQuery,
    CourseResponse,
    EventQuery,
    EventRegistrationCreate,
    EventResponse,
)
from services.chat_service import (
    cancel_registration,
    create_or_get_session,
    get_course_by_id,
    get_event_by_id,
    get_session_by_id,
    get_session_messages,
    query_courses,
    query_events,
    register_for_event,
    save_message,
)
from utils.database import get_db
from utils.exceptions import BusinessError, NotFoundError
from utils.response import error_response, paginated_response, success_response
from utils.security import verify_dify_service_token

router = APIRouter(prefix="/api/v1", tags=["客服 Agent"])
_SQLITE_REGISTRATION_LOCK = RLock()


def _is_sqlite_session(db: Session) -> bool:
    """判断当前测试/运行 Session 是否绑定 SQLite。"""
    bind = db.get_bind()
    return bool(bind and bind.dialect.name == "sqlite")


@router.get(
    "/courses",
    summary="查询课程列表",
    description="""
查询课程列表，支持按分类、关键词、价格区间筛选。

**数据来源**：course_project 表
**默认**：只返回 status=1 的课程
**Dify白名单**：✅
""",
)
def list_courses(
    category: Optional[str] = Query(default=None, description="课程分类"),
    keyword: Optional[str] = Query(default=None, description="关键词搜索"),
    min_price: Optional[Decimal] = Query(default=None, description="最低价格"),
    max_price: Optional[Decimal] = Query(default=None, description="最高价格"),
    status: Optional[int] = Query(default=1, description="1=上架 0=下架"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_dify_service_token),
):
    # 白名单接口由 verify_dify_service_token 保护，只有 Dify HTTP 节点可直接调用。
    params = CourseQuery(
        category=category,
        keyword=keyword,
        min_price=min_price,
        max_price=max_price,
        status=status,
        page=page,
        page_size=page_size,
    )
    items, total = query_courses(db, params)
    # 所有列表接口统一返回 {items,total,page,page_size}，便于 Dify/前端复用。
    return paginated_response(
        items=[CourseResponse.model_validate(item).model_dump() for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/courses/{course_id}",
    summary="查询课程详情",
    description="查询单个课程详情。**数据来源**：course_project 表",
)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
):
    # 详情接口不在 Dify 白名单内，主要供前端或 Swagger 调试使用。
    course = get_course_by_id(db, course_id)
    if not course:
        raise NotFoundError("课程不存在")
    return success_response(data=CourseResponse.model_validate(course).model_dump())


@router.get(
    "/events",
    summary="查询活动列表",
    description="""
查询活动列表，支持按状态、类型、日期筛选。

**数据来源**：event_lecture 表
**默认**：只返回 status=upcoming 的活动
**Dify白名单**：✅
""",
)
def list_events(
    status: Optional[str] = Query(default="upcoming", description="upcoming/ongoing/ended/cancelled"),
    event_type: Optional[str] = Query(default=None, description="online/offline/hybrid"),
    start_date: Optional[str] = Query(default=None, description="开始日期"),
    end_date: Optional[str] = Query(default=None, description="结束日期"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_dify_service_token),
):
    # 查询接口是 Dify 白名单能力之一，返回的数据必须来自 event_lecture 表。
    params = EventQuery(
        status=status,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    items, total = query_events(db, params)
    return paginated_response(
        items=[EventResponse.model_validate(item).model_dump() for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/events/{event_id}",
    summary="查询活动详情",
    description="查询单个活动详情。**数据来源**：event_lecture 表",
)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
):
    # 详情接口不在 Dify 白名单内，供后台/调试查看单个活动。
    event = get_event_by_id(db, event_id)
    if not event:
        raise NotFoundError("活动不存在")
    return success_response(data=EventResponse.model_validate(event).model_dump())


@router.post(
    "/events/{event_id}/register",
    summary="活动报名",
    description="""
用户报名参加指定活动。

**业务规则：**
- 活动必须存在且状态为 upcoming
- 报名人数不得超过最大人数
- 同一用户不允许重复报名（uk_event_user 唯一索引兜底）
- 并发报名使用 SELECT ... FOR UPDATE 行锁
- 无物理外键：应用层校验 event_id 和 user_id 对应记录存在

**Dify白名单**：✅
""",
    responses={
        200: {"description": "报名成功"},
        404: {"description": "活动不存在或用户不存在"},
        409: {"description": "重复报名或状态冲突"},
        422: {"description": "名额已满"},
    },
)
def register_event(
    event_id: int,
    data: EventRegistrationCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_dify_service_token),
):
    # SQLite 的测试 Session 不是线程安全的；生产 MySQL 依赖 Service 层行锁处理并发。
    if _is_sqlite_session(db):
        with _SQLITE_REGISTRATION_LOCK:
            return _register_event(event_id, data, db)
    return _register_event(event_id, data, db)


@router.post(
    "/dify/events/{event_id}/register",
    summary="Dify活动报名兼容接口",
    description="""
Dify 工作流专用报名接口。

该接口复用正式报名逻辑，但会把重复报名、活动不存在、名额已满等业务状态
统一转换为 HTTP 200 + 业务 code，避免 Dify HTTP 节点在 4xx 时中断流程。

认证失败仍返回 HTTP 403，用于暴露 Dify Service Token 配置错误。
""",
    responses={
        200: {"description": "报名成功或可解析的业务状态"},
        403: {"description": "Dify Service Token 无效"},
    },
)
def dify_register_event(
    event_id: int,
    data: EventRegistrationCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_dify_service_token),
):
    if _is_sqlite_session(db):
        with _SQLITE_REGISTRATION_LOCK:
            return _register_event_for_dify(event_id, data, db)
    return _register_event_for_dify(event_id, data, db)


def _register_event(event_id: int, data: EventRegistrationCreate, db: Session):
    """执行报名并提交事务，供 MySQL 正常路径和 SQLite 测试串行路径复用。"""
    try:
        registration = register_for_event(db, event_id, data)
        db.commit()

        # 获取活动名称用于响应
        event = get_event_by_id(db, event_id)

        return success_response(
            data={
                "id": registration.id,
                "event_id": registration.event_id,
                "event_name": event.event_name if event else None,
                "user_id": registration.user_id,
                "customer_name": registration.customer_name,
                "contact_info": registration.contact_info,
                "status": registration.status,
                "create_time": registration.create_time.isoformat(),
            },
            message="报名成功",
        )
    except BusinessError:
        # 业务异常未修改持久化状态，交给全局异常处理保持统一响应格式。
        raise
    except Exception:
        db.rollback()
        raise


def _register_event_for_dify(event_id: int, data: EventRegistrationCreate, db: Session):
    """Return business errors as HTTP 200 bodies so Dify can keep routing."""
    try:
        return _register_event(event_id, data, db)
    except BusinessError as exc:
        if not _is_sqlite_session(db):
            db.rollback()
        if isinstance(exc.detail, dict):
            return exc.detail
        return error_response(50001, str(exc.detail))


@router.delete(
    "/events/{event_id}/register",
    summary="取消报名",
    description="取消已报名的活动。仅支持 status=registered 的报名记录。",
)
def cancel_event_registration(
    event_id: int,
    user_id: int = Query(..., description="用户ID"),
    db: Session = Depends(get_db),
):
    # 取消报名不是 Dify 白名单接口，保持为普通后台/调试接口。
    try:
        registration = cancel_registration(db, event_id, user_id)
        db.commit()
        return success_response(
            data={
                "id": registration.id,
                "event_id": registration.event_id,
                "status": registration.status,
            },
            message="已取消报名",
        )
    except BusinessError:
        # NotFound/State 等业务错误保留原始错误码，不做额外包装。
        raise
    except Exception:
        db.rollback()
        raise


@router.post(
    "/chat/session",
    summary="创建/获取会话",
    description="""
创建新客服会话或获取已有活跃会话。

**业务规则：**
- 如果提供 user_id，优先返回该用户的活跃会话
- 否则创建新会话（生成唯一 session_id）

**Dify白名单**：✅
""",
)
def create_session(
    data: ChatSessionCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_dify_service_token),
):
    try:
        # 会话创建是 Dify 白名单能力，用于把 Dify conversation 与业务会话打通。
        session = create_or_get_session(db, data)
        db.commit()
        db.refresh(session)
        return success_response(
            data=ChatSessionResponse.model_validate(session).model_dump(),
            message="会话已创建/获取",
        )
    except BusinessError:
        # 业务异常已携带规范错误码，直接抛给全局异常处理。
        raise
    except Exception:
        db.rollback()
        raise


@router.post(
    "/chat/session/{session_id}/messages",
    summary="保存消息",
    description="保存客服会话中的消息记录。**数据来源**：chat_message 表",
)
def create_message(
    session_id: str,
    data: ChatMessageCreate,
    db: Session = Depends(get_db),
):
    try:
        # 消息接口不强制 Dify Service Token，便于前端/服务端保存会话历史。
        message = save_message(db, session_id, data)
        db.commit()
        db.refresh(message)
        return success_response(
            data=ChatMessageResponse.model_validate(message).model_dump(),
            message="消息已保存",
        )
    except BusinessError:
        # 会话不存在等业务错误统一走 BusinessError 响应。
        raise
    except Exception:
        db.rollback()
        raise


@router.get(
    "/chat/session/{session_id}/messages",
    summary="查询消息历史",
    description="获取会话消息记录（游标分页，适用于大数据量场景）",
)
def list_messages(
    session_id: str,
    cursor: Optional[int] = Query(default=None, description="游标ID"),
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    # 先校验会话存在，避免不存在的 session_id 返回空列表掩盖调用错误。
    session = get_session_by_id(db, session_id)
    if not session:
        raise NotFoundError("会话不存在")

    items, next_cursor, has_more = get_session_messages(db, session_id, cursor, limit)
    return success_response(data={
        "items": [ChatMessageResponse.model_validate(item).model_dump() for item in items],
        "next_cursor": next_cursor,
        "has_more": has_more,
    })
