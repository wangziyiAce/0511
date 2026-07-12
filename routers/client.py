"""浏览器安全代理路由。

本文件把原本仅供 Dify 工作流调用的课程、活动和会话能力转换为普通 JWT 登录态接口。
前端请求到达这里后由当前用户身份完成授权，Dify Service Token 不会传给浏览器。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from schemas.chat import ChatMessageCreate, ChatMessageResponse, ChatSessionCreate, ChatSessionResponse, CourseQuery, CourseResponse, EventQuery, EventRegistrationCreate, EventResponse
from services.chat_service import (cancel_registration, create_or_get_session, get_course_by_id, get_event_by_id,
    get_session_by_id, get_session_messages, query_courses, query_events, register_for_event, save_message)
from utils.auth import CurrentUser, get_current_user
from utils.database import get_db
from utils.response import paginated_response, success_response

router = APIRouter(prefix='/api/v1/client', tags=['前端安全代理'])

@router.get('/courses')
def list_courses(page: int = 1, page_size: int = 20, keyword: str | None = None, category: str | None = None,
                 current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """为已登录用户返回课程列表，避免前端使用 Dify Service Token。"""
    items, total = query_courses(db, CourseQuery(page=page, page_size=page_size, keyword=keyword, category=category))
    return paginated_response(items=[CourseResponse.model_validate(item).model_dump() for item in items], total=total, page=page, page_size=page_size)

@router.get('/courses/{course_id}')
def get_course(course_id: int, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """读取单个课程详情；数据仍由既有课程 Service 查询。"""
    item = get_course_by_id(db, course_id)
    if not item: raise HTTPException(status_code=404, detail='课程不存在')
    return success_response(data=CourseResponse.model_validate(item).model_dump())

@router.get('/events')
def list_events(page: int = 1, page_size: int = 20, status: str | None = 'upcoming',
                current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """按登录态查询活动，浏览器不接触 Dify 专用鉴权。"""
    items, total = query_events(db, EventQuery(page=page, page_size=page_size, status=status))
    return paginated_response(items=[EventResponse.model_validate(item).model_dump() for item in items], total=total, page=page, page_size=page_size)

@router.get('/events/{event_id}')
def get_event(event_id: int, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """读取活动详情。"""
    item = get_event_by_id(db, event_id)
    if not item: raise HTTPException(status_code=404, detail='活动不存在')
    return success_response(data=EventResponse.model_validate(item).model_dump())

@router.post('/events/{event_id}/register')
def register_event(event_id: int, request: EventRegistrationCreate, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """用当前登录用户报名，忽略前端伪造的 user_id。"""
    registration = register_for_event(db, event_id, request.model_copy(update={'user_id': current_user.id}))
    db.commit(); db.refresh(registration)
    return success_response(data={'id': registration.id, 'event_id': registration.event_id, 'status': registration.status})

@router.delete('/events/{event_id}/register')
def cancel_event(event_id: int, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """仅取消当前用户自己的报名记录，避免由查询参数跨用户操作。"""
    registration = cancel_registration(db, event_id, current_user.id)
    db.commit()
    return success_response(data={'id': registration.id, 'status': registration.status})

@router.post('/chat/sessions')
def create_session(request: ChatSessionCreate, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建或复用当前用户会话。"""
    session = create_or_get_session(db, request.model_copy(update={'user_id': current_user.id}))
    db.commit(); db.refresh(session)
    return success_response(data=ChatSessionResponse.model_validate(session).model_dump())

@router.get('/chat/sessions/{session_id}')
def get_session(session_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """读取会话前确认其归属当前用户。"""
    session = get_session_by_id(db, session_id)
    if not session or session.user_id != current_user.id: raise HTTPException(status_code=404, detail='会话不存在')
    return success_response(data=ChatSessionResponse.model_validate(session).model_dump())

@router.get('/chat/sessions/{session_id}/messages')
def list_messages(session_id: str, cursor: int | None = Query(default=None), limit: int = 20,
                  current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回当前用户会话的游标消息历史。"""
    session = get_session_by_id(db, session_id)
    if not session or session.user_id != current_user.id: raise HTTPException(status_code=404, detail='会话不存在')
    items, next_cursor, has_more = get_session_messages(db, session_id, cursor, limit)
    return success_response(data={'items': [ChatMessageResponse.model_validate(item).model_dump() for item in items], 'next_cursor': next_cursor, 'has_more': has_more})

@router.post('/chat/sessions/{session_id}/messages')
def create_message(session_id: str, request: ChatMessageCreate, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """保存消息前验证会话归属，防止跨用户写入。"""
    session = get_session_by_id(db, session_id)
    if not session or session.user_id != current_user.id: raise HTTPException(status_code=404, detail='会话不存在')
    message = save_message(db, session_id, request)
    db.commit(); db.refresh(message)
    return success_response(data=ChatMessageResponse.model_validate(message).model_dump())
