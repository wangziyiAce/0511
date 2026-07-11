"""
学生智能助手 API 路由 — 对齐 API 接口规范 V1.2 §7

端点清单:
    P0 (MVP 必做):
        POST   /student/leave-requests              — 提交请假申请
        PUT    /student/leave-requests/{id}/approve  — 审批请假
        POST   /student/feedback-tickets             — 提交投诉/建议
        PUT    /student/feedback-tickets/{id}        — 处理投诉

    P1 (建议完成):
        GET    /student/leave-requests               — 查询请假记录
        GET    /student/feedback-tickets             — 查询投诉列表
        POST   /student/psych/record                 — 记录心理交互 (Dify白名单)
        GET    /student/psych/alerts                 — 查询心理预警
        PUT    /student/psych/alerts/{id}            — 处理心理预警
        GET    /student/applications                 — 查询申请进度 (Dify白名单)
        GET    /student/deadlines                    — 查询学业DDL
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from utils.database import get_db
from services.student_service import StudentService
from schemas.student import (
    LeaveCreate, LeaveApprove,
    FeedbackCreate, FeedbackUpdate,
    PsychRecordCreate, PsychAlertUpdate,
    IntentCreate,
)

router = APIRouter()


# ===== 统一响应辅助 =====

def _ok(data=None, message="success"):
    return {"code": 0, "message": message, "data": data}


def _paginated(items, total, page, page_size):
    return {"code": 0, "message": "success", "data": {
        "items": items, "total": total, "page": page, "page_size": page_size
    }}


# =========================================================================
# 请假管理
# =========================================================================
# P0: POST (提交) + PUT (审批)
# P1: GET (查询)
# 状态流转: pending → approved / rejected / cancelled (均为终态)
# =========================================================================

@router.post(
    "/leave-requests",
    summary="提交请假申请 [P0]",
    description="""
学生提交请假申请。

**业务规则：**
- 双重逻辑外键校验：sys_user (user_type='student') + student_info (status='active')
- end_time 必须晚于 start_time
- 新建状态为 pending

数据写入 student_admin_service 表 (service_type='leave')。
""",
)
def create_leave_request(body: LeaveCreate, db: Session = Depends(get_db)):
    svc = StudentService(db)
    leave = svc.create_leave_request(body)
    return _ok({
        "id": leave.id, "student_id": leave.student_id,
        "service_type": leave.service_type, "leave_type": leave.leave_type,
        "start_time": str(leave.start_time) if leave.start_time else None,
        "end_time": str(leave.end_time) if leave.end_time else None,
        "status": leave.status,
        "create_time": str(leave.create_time) if leave.create_time else None,
    }, "请假申请已提交")


@router.put(
    "/leave-requests/{request_id}/approve",
    summary="审批请假 [P0]",
    description="""
班主任/管理员审批请假申请。

**业务规则：**
- 仅 pending 状态可审批
- 条件 UPDATE WHERE status='pending' 防并发
- 审批后状态变为 approved/rejected（终态，不可回退）
""",
)
def approve_leave(request_id: int, body: LeaveApprove, db: Session = Depends(get_db)):
    svc = StudentService(db)
    leave = svc.approve_leave(request_id, body)
    return _ok({
        "id": leave.id, "status": leave.status,
        "approver_id": leave.approver_id,
        "approval_comment": leave.approval_comment,
        "approval_time": str(leave.approval_time) if leave.approval_time else None,
    }, "审批完成")


@router.put(
    "/leave-requests/{request_id}/cancel",
    summary="撤销请假 [P1]",
    description="""
学生自主撤销待审批的请假申请。

**业务规则：**
- 仅 pending 状态可撤销
- 仅本人可撤销
- 撤销后状态变为 cancelled（终态）
""",
)
def cancel_leave(
    request_id: int,
    student_id: int = Query(..., gt=0, description="学生ID"),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    leave = svc.cancel_leave(request_id, student_id)
    return _ok({
        "id": leave.id, "status": leave.status,
    }, "请假已撤销")


@router.get("/leave-requests", summary="查询请假记录 [P1]")
def list_leaves(
    student_id: int = Query(..., gt=0),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_leaves(student_id, status, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


# =========================================================================
# 售后反馈
# =========================================================================
# P0: POST (提交) + PUT (处理)
# P1: GET (查询)
# 状态流转: pending → processing → resolved → closed (终态)
# =========================================================================

@router.post(
    "/feedback-tickets",
    summary="提交投诉/建议 [P0]",
    description="""
学生提交投诉、建议或咨询工单。

**业务规则：**
- 匿名投诉 student_id 可为 NULL
- 非匿名时校验 student_id → sys_user (user_type='student')
- 自动判定优先级（退款/律师 → urgent，投诉/紧急 → high）
""",
)
def create_feedback(body: FeedbackCreate, db: Session = Depends(get_db)):
    svc = StudentService(db)
    ticket = svc.create_feedback(body)
    return _ok({
        "id": ticket.id, "ticket_type": ticket.ticket_type,
        "category": ticket.category, "status": ticket.status,
        "priority": ticket.priority,
        "create_time": str(ticket.create_time) if ticket.create_time else None,
    }, "工单已创建")


@router.put(
    "/feedback-tickets/{ticket_id}",
    summary="处理投诉 [P0]",
    description="""
处理投诉工单 — 更新状态、分配处理人、记录解决方案。

**状态流转:** pending → processing → resolved → closed (终态)
closed 为终态，不可回退。
""",
)
def update_feedback(ticket_id: int, body: FeedbackUpdate, db: Session = Depends(get_db)):
    svc = StudentService(db)
    ticket = svc.update_feedback(ticket_id, body)
    return _ok({
        "id": ticket.id, "status": ticket.status,
        "solution": ticket.solution, "assignee_id": ticket.assignee_id,
        "update_time": str(ticket.update_time) if ticket.update_time else None,
    }, "工单已处理")


@router.get("/feedback-tickets", summary="查询投诉列表 [P1]")
def list_feedbacks(
    student_id: int = Query(..., gt=0),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_feedbacks(student_id, status, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


# =========================================================================
# 心理健康
# =========================================================================
# P1: POST psych/record (Dify白名单), GET psych/alerts, PUT psych/alerts
# 预警: low (仅记录) / medium (创建预警+班主任跟进) / high (立即预警+人工介入)
# =========================================================================

@router.post(
    "/psych/record",
    summary="记录心理交互 [P1] [Dify白名单]",
    description="""
保存 Dify AI 识别的学生情绪状态，联动更新心理画像，条件触发预警。

**预警触发:** emotion_score < 20 或高危关键词 → high | 20-39 → medium | >= 40 → low
**重要:** AI 只做风险识别，不做医学诊断。高危预警必须人工介入。
""",
)
def record_psych(body: PsychRecordCreate, db: Session = Depends(get_db)):
    # 兼容 Dify 传入逗号分隔字符串
    if isinstance(body.trigger_keywords, str):
        keywords = [k.strip() for k in body.trigger_keywords.split(",") if k.strip()]
        body = body.model_copy(update={"trigger_keywords": keywords or None})
    svc = StudentService(db)
    result = svc.record_psych(body)
    return _ok(result, "心理记录已保存")


@router.get("/psych/alerts", summary="查询心理预警列表 [P1]")
def list_psych_alerts(
    risk_level: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_psych_alerts(risk_level, status, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


@router.put(
    "/psych/alerts/{alert_id}",
    summary="处理心理预警 [P1]",
    description="""
班主任/管理员处理心理预警。

**状态流转:** pending → following → resolved (已解除) / dismissed (误报)
""",
)
def update_psych_alert(alert_id: int, body: PsychAlertUpdate, db: Session = Depends(get_db)):
    svc = StudentService(db)
    alert = svc.update_psych_alert(alert_id, body)
    return _ok({
        "id": alert.id, "status": alert.status,
        "teacher_id": alert.teacher_id,
        "follow_record": alert.follow_record,
        "resolved_time": str(alert.resolved_time) if alert.resolved_time else None,
    }, "预警已处理")


# =========================================================================
# 申请进度
# =========================================================================
# P1: GET (Dify白名单)
# =========================================================================

@router.get(
    "/applications",
    summary="查询留学申请进度 [P1] [Dify白名单]",
    description="查询学生的留学申请进度列表。数据来源: application_progress 表。",
)
def list_applications(
    student_id: int = Query(..., gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_applications(student_id, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


# =========================================================================
# 成绩查询
# =========================================================================

@router.get(
    "/scores",
    summary="查询学生成绩 [P1]",
    description="查询学生各课程成绩，支持按学期筛选。数据来源: student_score 表。",
)
def list_scores(
    student_id: int = Query(..., gt=0, description="学生ID"),
    semester: str = Query(None, description="学期筛选，如 2025-2026-1"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_scores(student_id, semester, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


# =========================================================================
# 学业DDL
# =========================================================================
# P1: GET
# =========================================================================

@router.get(
    "/deadlines",
    summary="查询学业DDL [P1]",
    description="查询学生近期截止事项。默认返回未来30天内未完成的DDL。",
)
def list_deadlines(
    student_id: int = Query(..., gt=0),
    upcoming_days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_deadlines(student_id, upcoming_days, page, page_size)
    return _paginated(result["items"], result["total"], page, page_size)


# =========================================================================
# 通知中心（学生站内收件箱）
# =========================================================================
# P1: GET (查询) / PUT (标记已读) / PUT read-all (全部已读)
# 由各业务状态变更自动写入：请假审批、投诉处理、心理预警、DDL提醒、进度更新
# =========================================================================

@router.get(
    "/notifications",
    summary="查询我的通知 [P1]",
    description="查询学生站内通知。only_unread=true 仅看未读；返回含 unread_count 供前端小红点。",
)
def list_notifications(
    student_id: int = Query(..., gt=0),
    only_unread: bool = Query(False, description="仅返回未读"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    result = svc.list_notifications(student_id, only_unread, page, page_size)
    return _ok({
        "items": result["items"],
        "total": result["total"],
        "unread_count": result["unread_count"],
        "page": page,
        "page_size": page_size,
    })


@router.put(
    "/notifications/{notification_id}/read",
    summary="标记通知已读 [P1]",
    description="标记单条通知为已读（需校验归属学生）。",
)
def mark_notification_read(
    notification_id: int,
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    note = svc.mark_notification_read(notification_id, student_id)
    return _ok({"id": note.id, "is_read": note.is_read}, "已标记为已读")


@router.put(
    "/notifications/read-all",
    summary="全部标记已读 [P1]",
    description="将学生所有未读通知一键置为已读。",
)
def mark_all_read(
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    cnt = svc.mark_all_read(student_id)
    return _ok({"updated": cnt}, "已全部标记为已读")


# =========================================================================
# 增值转化 — 意向标签
# =========================================================================
# P2: POST (Dify 对话识别后写入) / GET (查询) / GET recommendations (推荐)
# =========================================================================

@router.post(
    "/intent",
    summary="记录学生意向 [P2]",
    description="记录学生升学/转化意向（Dify 对话识别后调用）。",
)
def create_intent(body: IntentCreate, db: Session = Depends(get_db)):
    svc = StudentService(db)
    tag = svc.create_intent(body)
    return _ok({
        "id": tag.id, "student_id": tag.student_id,
        "intent_type": tag.intent_type, "intent_name": tag.intent_name,
        "source": tag.source, "score": tag.score, "remark": tag.remark,
        "create_time": str(tag.create_time) if tag.create_time else None,
    }, "意向已记录")


@router.get(
    "/intent",
    summary="查询学生意向 [P2]",
    description="查询该学生的全部意向标签（按强度降序）。",
)
def list_intents(
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    tags = svc.list_intents(student_id)
    return _ok({
        "items": [{
            "id": t.id, "student_id": t.student_id,
            "intent_type": t.intent_type, "intent_name": t.intent_name,
            "source": t.source, "score": t.score, "remark": t.remark,
            "create_time": str(t.create_time) if t.create_time else None,
        } for t in tags],
        "total": len(tags),
    })


@router.get(
    "/recommendations",
    summary="获取增值转化推荐 [P2]",
    description="基于学生意向标签，返回匹配的学历提升/增值项目推荐（Dify 可据此生成话术）。",
)
def get_recommendations(
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)
    recs = svc.get_recommendations(student_id)
    return _ok({"items": recs, "total": len(recs)})
