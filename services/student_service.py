"""
学生智能助手 — 业务逻辑层

职责:
    1. 业务规则校验（状态机、数据合法性）
    2. 逻辑外键存在性校验（无物理外键场景，使用 EXISTS 子查询）
    3. 事务管理（事务中不调用外部 API）

对齐文档:
    - 数据库设计规范 V2.1 §5、§6.6、§14
    - API 接口规范 V1.2 §7、§14
"""
from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import update, text
from fastapi import HTTPException

from models.student import (
    StudentInfo, StudentScore, StudentAdminService,
    StudentPsychProfile, StudentPsychRecord, StudentPsychAlert,
    StudentFeedbackTicket, ApplicationProgress, AcademicDeadline,
    StudentNotification, StudentIntentTag,
)


# =============================================================================
# 逻辑外键校验 — 表名硬编码，参数化绑定，无 SQL 注入风险
# =============================================================================

def _user_exists(db: Session, user_id: int, user_type: Optional[str] = None) -> bool:
    """校验 sys_user 中存在指定类型的正常用户"""
    if user_type:
        sql = text(
            "SELECT EXISTS(SELECT 1 FROM sys_user"
            " WHERE id=:id AND user_type=:ut AND status='normal') AS result"
        )
        return bool(db.execute(sql, {"id": user_id, "ut": user_type}).scalar())
    sql = text(
        "SELECT EXISTS(SELECT 1 FROM sys_user"
        " WHERE id=:id AND status='normal') AS result"
    )
    return bool(db.execute(sql, {"id": user_id}).scalar())


def _student_user_exists(db: Session, student_id: int) -> bool:
    """校验 sys_user 中存在正常学生用户"""
    return _user_exists(db, student_id, "student")


# =============================================================================
# 错误响应辅助 — 对齐 API 规范 V1.2 §3.3 {code, message, data}
# =============================================================================

def _raise(code: int, message: str, status_code: int = 400):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "data": None},
    )


# =============================================================================
# StudentService
# =============================================================================

class StudentService:
    """学生业务服务"""

    def __init__(self, db: Session):
        self.db = db

    def _commit(self):
        """安全提交，统一异常处理"""
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            _raise(50001, f"数据库操作失败: {str(e)[:200]}", 500)

    # =========================================================================
    # 请假管理
    # =========================================================================

    def create_leave_request(self, data) -> StudentAdminService:
        """提交请假申请 — 双重逻辑外键校验"""
        if not _student_user_exists(self.db, data.student_id):
            _raise(40402, f"学生用户不存在: id={data.student_id}", 404)

        info = self.db.query(StudentInfo).filter(
            StudentInfo.user_id == data.student_id,
            StudentInfo.status == "active",
        ).first()
        if not info:
            _raise(40402, f"学生档案不存在或已离校: id={data.student_id}", 404)

        if data.end_time <= data.start_time:
            _raise(40001, "结束时间必须晚于开始时间", 400)

        leave = StudentAdminService(
            student_id=data.student_id,
            service_type=data.service_type,
            leave_type=data.leave_type,
            start_time=data.start_time if isinstance(data.start_time, datetime) else datetime.strptime(data.start_time, "%Y-%m-%d %H:%M"),
            end_time=data.end_time if isinstance(data.end_time, datetime) else datetime.strptime(data.end_time, "%Y-%m-%d %H:%M"),
            reason=data.reason,
            attachment_url=data.attachment_url,
            status="pending",
        )
        self.db.add(leave)
        # 通知班主任（teacher 也是 sys_user，复用 student_notification 表）
        if info.class_teacher_id:
            self._push_notification(info.class_teacher_id, "leave_submitted",
                "新的请假申请", f"学生提交了请假申请，等待审批")
        self._commit()
        self.db.refresh(leave)
        return leave

    def approve_leave(self, request_id: int, data) -> StudentAdminService:
        """审批请假 — 条件更新防并发 + 角色校验"""
        leave = self.db.query(StudentAdminService).filter(
            StudentAdminService.id == request_id,
            StudentAdminService.service_type == "leave",
        ).first()
        if not leave:
            _raise(40401, "请假申请不存在", 404)

        if leave.status != "pending":
            _raise(40902, f"请假状态为 {leave.status}，不可审批", 422)

        # 审批人必须是员工或管理员
        if not _user_exists(self.db, data.approver_id, "employee"):
            if not _user_exists(self.db, data.approver_id, "admin"):
                _raise(40301, "审批人必须是员工或管理员", 403)

        new_status = "approved" if data.action == "approve" else "rejected"
        result = self.db.execute(
            update(StudentAdminService)
            .where(
                StudentAdminService.id == request_id,
                StudentAdminService.status == "pending",
            )
            .values(
                status=new_status,
                approver_id=data.approver_id,
                approval_comment=data.approval_comment,
                approval_time=datetime.now(),
                update_time=datetime.now(),
            )
        )
        if result.rowcount == 0:
            _raise(40901, "请假状态已被其他操作修改，请刷新后重试", 409)

        # 写入学生通知（仅 add，统一在 _commit 落库）
        approved = new_status == "approved"
        self._push_notification(
            leave.student_id,
            "leave_approved" if approved else "leave_rejected",
            f"请假申请{'已批准' if approved else '被驳回'}",
            f"您的请假申请（{leave.leave_type or '请假'}，"
            f"{leave.start_time} 至 {leave.end_time}）"
            f"{'已批准' if approved else '被驳回'}。"
            f"{('审批意见：' + data.approval_comment) if data.approval_comment else ''}",
            related_type="leave", related_id=request_id,
        )

        self._commit()
        self.db.refresh(leave)
        return leave

    def cancel_leave(self, request_id: int, student_id: int) -> StudentAdminService:
        """学生自主撤销请假"""
        leave = self.db.query(StudentAdminService).filter(
            StudentAdminService.id == request_id,
            StudentAdminService.service_type == "leave",
        ).first()
        if not leave:
            _raise(40401, "请假申请不存在", 404)
        if leave.student_id != student_id:
            _raise(40301, "只能撤销本人的请假申请", 403)
        if leave.status != "pending":
            _raise(40902, f"请假状态为 {leave.status}，不可撤销", 422)

        result = self.db.execute(
            update(StudentAdminService)
            .where(
                StudentAdminService.id == request_id,
                StudentAdminService.status == "pending",
            )
            .values(status="cancelled", update_time=datetime.now())
        )
        if result.rowcount == 0:
            _raise(40901, "请假状态已被修改，请刷新后重试", 409)

        self._commit()
        self.db.refresh(leave)
        return leave

    def list_leaves(
        self, student_id: int, status: Optional[str] = None,
        page: int = 1, page_size: int = 20
    ) -> dict:
        return self._paginate(
            self.db.query(StudentAdminService).filter(
                StudentAdminService.service_type == "leave",
                StudentAdminService.student_id == student_id,
            ),
            status, StudentAdminService.status, StudentAdminService.create_time,
            page, page_size,
        )

    # =========================================================================
    # 售后反馈
    # =========================================================================

    def create_feedback(self, data) -> StudentFeedbackTicket:
        """提交投诉/建议 — student_id 必填（DB 约束 NOT NULL）"""
        if not _student_user_exists(self.db, data.student_id):
            _raise(40402, f"学生用户不存在: id={data.student_id}", 404)

        priority = "medium"
        content_text = (data.content or "") + (data.detail or "")
        if any(w in content_text for w in ["退款", "律师", "起诉"]):
            priority = "urgent"
        elif any(w in content_text for w in ["投诉", "严重", "紧急", "曝光"]):
            priority = "high"

        ticket = StudentFeedbackTicket(
            student_id=data.student_id,
            ticket_type=data.ticket_type,
            category=data.category,
            title=data.title,
            content=data.content,
            detail=data.detail,
            status="pending",
            priority=priority,
        )
        self.db.add(ticket)
        self._commit()
        self.db.refresh(ticket)
        return ticket

    def update_feedback(self, ticket_id: int, data) -> StudentFeedbackTicket:
        """处理投诉"""
        ticket = self.db.query(StudentFeedbackTicket).filter(
            StudentFeedbackTicket.id == ticket_id
        ).first()
        if not ticket:
            _raise(40401, "工单不存在", 404)

        VALID_TRANSITIONS = {
            "pending": ["processing"],
            "processing": ["resolved"],
            "resolved": ["closed"],
            "closed": [],
        }
        if data.status not in VALID_TRANSITIONS.get(ticket.status, []):
            _raise(40902,
                   f"工单状态不允许从 {ticket.status} 变更为 {data.status}", 422)

        if data.assignee_id is not None:
            if not _user_exists(self.db, data.assignee_id):
                _raise(40402, f"处理人不存在: id={data.assignee_id}", 404)

        ticket.status = data.status
        if data.assignee_id is not None:
            ticket.assignee_id = data.assignee_id
        if data.solution is not None:
            ticket.solution = data.solution

        # 工单处理完成（已解决/已关闭）后通知学生
        if data.status in ("resolved", "closed"):
            self._push_notification(
                ticket.student_id, "feedback_resolved",
                "您的反馈已处理完成",
                f"您提交的工单「{ticket.title or ticket.content[:20]}」"
                f"已{'解决' if data.status == 'resolved' else '关闭'}。"
                f"{('处理结果：' + data.solution) if data.solution else ''}",
                related_type="feedback", related_id=ticket_id,
            )

        self._commit()
        self.db.refresh(ticket)
        return ticket

    def list_feedbacks(
        self, student_id: int, status: Optional[str] = None,
        page: int = 1, page_size: int = 20
    ) -> dict:
        return self._paginate(
            self.db.query(StudentFeedbackTicket).filter(
                StudentFeedbackTicket.student_id == student_id,
            ),
            status, StudentFeedbackTicket.status, StudentFeedbackTicket.create_time,
            page, page_size,
        )

    # =========================================================================
    # 心理健康 — 核心预警联动
    # =========================================================================

    HIGH_RISK_WORDS = [
        "自杀", "轻生", "不想活", "死了算了", "活着没意思",
        "自残", "割腕", "跳楼", "安眠药", "结束生命",
        "绝望", "崩溃", "撑不下去了", "没希望了", "想死",
    ]

    def record_psych(self, data) -> dict:
        """记录心理交互 — 联动更新画像 + 条件创建预警"""
        if not _student_user_exists(self.db, data.student_id):
            _raise(40402, f"学生不存在: id={data.student_id}", 404)

        record = StudentPsychRecord(
            student_id=data.student_id,
            emotion_tag=data.emotion_tag,
            emotion_score=data.emotion_score,
            interaction_content=data.interaction_content,
            trigger_keywords=data.trigger_keywords,
            record_date=datetime.strptime(data.record_date, "%Y-%m-%d").date() if data.record_date else date.today(),
        )
        self.db.add(record)

        # 更新或创建心理画像（ORM 方式，避免数据库方言绑定）
        now = datetime.now()
        profile = self.db.query(StudentPsychProfile).filter(
            StudentPsychProfile.student_id == data.student_id
        ).first()

        if profile:
            profile.latest_emotion_tag = data.emotion_tag
            profile.emotion_score = data.emotion_score
            profile.last_interaction_time = now
            profile.update_time = now
        else:
            profile = StudentPsychProfile(
                student_id=data.student_id,
                latest_emotion_tag=data.emotion_tag,
                emotion_score=data.emotion_score,
                last_interaction_time=now,
                risk_level="low",
                create_time=now,
                update_time=now,
            )
            self.db.add(profile)

        self.db.flush()

        alert_created = False
        alert_id = None
        risk_level = self._determine_risk_level(data)

        if risk_level in ("medium", "high"):
            alert = StudentPsychAlert(
                student_id=data.student_id,
                trigger_reason=(
                    f"情绪分值 {data.emotion_score}，"
                    f"标签: {data.emotion_tag}，"
                    f"关键词: {data.trigger_keywords or '无'}"
                )[:500],
                risk_level=risk_level,
                status="pending",
            )
            self.db.add(alert)
            self.db.flush()
            alert_created = True
            alert_id = alert.id

        # 更新画像风险等级
        profile.risk_level = risk_level

        # 高危/中危：通知班主任介入
        if risk_level in ("high", "medium") and alert_id:
            student_info = self.db.query(StudentInfo).filter(
                StudentInfo.user_id == data.student_id
            ).first()
            teacher_id = student_info.class_teacher_id if student_info else None
            if teacher_id:
                self._push_notification(
                    teacher_id, "psych_alert",
                    f"⚠ 心理预警（{risk_level}）",
                    f"检测到学生情绪风险：分值{data.emotion_score}，关键词{data.trigger_keywords or '无'}。请及时介入。",
                    related_type="psych", related_id=alert_id,
                )
        # 高危表达：主动通知学生
        if risk_level == "high":
            self._push_notification(
                data.student_id, "psych_alert",
                "我们关注到了你最近的状态",
                "我们已注意到你最近的情绪状态，班主任/心理老师会尽快与你联系。"
                "你不是一个人，请记得寻求帮助。",
                related_type="psych", related_id=alert_id,
            )

        self._commit()
        return {
            "id": record.id, "student_id": data.student_id,
            "emotion_tag": data.emotion_tag, "emotion_score": data.emotion_score,
            "risk_level": risk_level,
            "alert_created": alert_created, "alert_id": alert_id,
        }

    def _determine_risk_level(self, data) -> str:
        """根据情绪分值 + 关键词判定风险等级"""
        if data.emotion_score < 20:
            return "high"
        keywords_str = " ".join(data.trigger_keywords or []) + " " + data.interaction_content
        if any(w in keywords_str for w in self.HIGH_RISK_WORDS):
            return "high"
        if data.emotion_score < 40:
            return "medium"
        return "low"

    def list_psych_alerts(
        self, risk_level: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        q = self.db.query(StudentPsychAlert)
        if risk_level:
            q = q.filter(StudentPsychAlert.risk_level == risk_level)
        if status:
            q = q.filter(StudentPsychAlert.status == status)
        return self._paginate(
            q, None, None, StudentPsychAlert.create_time, page, page_size,
        )

    def update_psych_alert(self, alert_id: int, data) -> StudentPsychAlert:
        """处理心理预警"""
        alert = self.db.query(StudentPsychAlert).filter(
            StudentPsychAlert.id == alert_id
        ).first()
        if not alert:
            _raise(40401, "预警不存在", 404)

        VALID_TRANSITIONS = {
            "pending": ["following"],
            "following": ["resolved", "dismissed"],
            "resolved": [], "dismissed": [],
        }
        if data.status not in VALID_TRANSITIONS.get(alert.status, []):
            _raise(40902,
                   f"预警状态不允许从 {alert.status} 变更为 {data.status}", 422)

        if not _user_exists(self.db, data.teacher_id):
            _raise(40402, f"老师不存在: id={data.teacher_id}", 404)

        alert.status = data.status
        alert.teacher_id = data.teacher_id
        if data.follow_record is not None:
            alert.follow_record = data.follow_record
        if data.status == "resolved":
            alert.resolved_time = datetime.now()
            # 跟进完成，通知学生
            self._push_notification(
                alert.student_id, "psych_alert",
                "心理关怀跟进已完成",
                "感谢你的信任，老师已完成本次心理关怀跟进。如需帮助可随时联系我们。",
                related_type="psych", related_id=alert_id,
            )

        self._commit()
        self.db.refresh(alert)
        return alert

    # =========================================================================
    # 申请进度
    # =========================================================================

    def list_applications(
        self, student_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        return self._paginate(
            self.db.query(ApplicationProgress).filter(
                ApplicationProgress.student_id == student_id,
            ),
            None, None, ApplicationProgress.update_time, page, page_size,
        )

    # =========================================================================
    # 成绩查询
    # =========================================================================

    def list_scores(
        self, student_id: int, semester: str = None,
        page: int = 1, page_size: int = 20
    ) -> dict:
        """查询学生成绩，支持按学期筛选"""
        q = self.db.query(StudentScore).filter(
            StudentScore.student_id == student_id,
        )
        if semester:
            q = q.filter(StudentScore.semester == semester)
        return self._paginate(
            q, None, None, StudentScore.create_time, page, page_size,
        )

    # =========================================================================
    # 学业DDL
    # =========================================================================

    def list_deadlines(
        self, student_id: int, upcoming_days: int = 30,
        page: int = 1, page_size: int = 20
    ) -> dict:
        today = date.today()
        cutoff = datetime.combine(
            today + timedelta(days=upcoming_days),
            datetime.max.time()
        )

        return self._paginate(
            self.db.query(AcademicDeadline).filter(
                AcademicDeadline.student_id == student_id,
                AcademicDeadline.status.in_(["pending", "reminded"]),
                AcademicDeadline.deadline >= today,
                AcademicDeadline.deadline <= cutoff,
            ),
            None, None, AcademicDeadline.deadline, page, page_size,
        )

    # =========================================================================
    # 通知中心
    # =========================================================================

    def _push_notification(
        self, student_id: int, ntype: str, title: str, content: str,
        related_type: Optional[str] = None, related_id: Optional[int] = None,
    ) -> StudentNotification:
        """写入一条学生通知（仅 add，由调用方统一 commit）"""
        note = StudentNotification(
            student_id=student_id,
            notify_type=ntype,
            title=title,
            content=content,
            related_type=related_type,
            related_id=related_id,
        )
        self.db.add(note)
        return note

    def list_notifications(
        self, student_id: int, only_unread: bool = False,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        q = self.db.query(StudentNotification).filter(
            StudentNotification.student_id == student_id
        )
        if only_unread:
            q = q.filter(StudentNotification.is_read == 0)
        unread_count = self.db.query(StudentNotification).filter(
            StudentNotification.student_id == student_id,
            StudentNotification.is_read == 0,
        ).count()
        total = q.count()
        items = q.order_by(StudentNotification.create_time.desc()) \
                  .offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "unread_count": unread_count, "items": items}

    def mark_notification_read(self, notification_id: int, student_id: int) -> StudentNotification:
        note = self.db.query(StudentNotification).filter(
            StudentNotification.id == notification_id,
            StudentNotification.student_id == student_id,
        ).first()
        if not note:
            _raise(40401, "通知不存在或不属于该学生", 404)
        note.is_read = 1
        note.update_time = datetime.now()
        self._commit()
        self.db.refresh(note)
        return note

    def mark_all_read(self, student_id: int) -> int:
        cnt = self.db.query(StudentNotification).filter(
            StudentNotification.student_id == student_id,
            StudentNotification.is_read == 0,
        ).update({
            StudentNotification.is_read: 1,
            StudentNotification.update_time: datetime.now(),
        })
        self._commit()
        return cnt

    # =========================================================================
    # 增值转化 — 意向标签
    # =========================================================================

    _PROJECT_POOL = {
        "master": "硕士升学规划与背景提升项目",
        "phd": "博士申请与科研能力打造项目",
        "transfer": "转专业 / 双学位衔接方案",
        "consult": "1 对 1 升学规划咨询",
        "other": "定制化留学增值服务",
    }

    def create_intent(self, data) -> StudentIntentTag:
        if not _student_user_exists(self.db, data.student_id):
            _raise(40402, f"学生用户不存在: id={data.student_id}", 404)
        tag = StudentIntentTag(
            student_id=data.student_id,
            intent_type=data.intent_type,
            intent_name=data.intent_name,
            source=data.source or "chat",
            score=data.score,
            remark=data.remark,
        )
        self.db.add(tag)
        self._commit()
        self.db.refresh(tag)
        return tag

    def list_intents(self, student_id: int) -> list:
        return self.db.query(StudentIntentTag).filter(
            StudentIntentTag.student_id == student_id
        ).order_by(
            StudentIntentTag.score.is_(None),   # 非空排前（MySQL 无 NULLS LAST）
            StudentIntentTag.score.desc(),
            StudentIntentTag.create_time.desc(),
        ).all()

    def get_recommendations(self, student_id: int) -> list:
        if not _student_user_exists(self.db, student_id):
            _raise(40402, f"学生用户不存在: id={student_id}", 404)
        tags = self.list_intents(student_id)
        return [{
            "intent_type": t.intent_type,
            "intent_name": t.intent_name,
            "matched_project": self._PROJECT_POOL.get(
                t.intent_type, self._PROJECT_POOL["other"]),
            "score": t.score,
        } for t in tags]

    # =========================================================================
    # 通用分页
    # =========================================================================

    def _paginate(self, query, status_filter, status_col, order_col,
                   page: int = 1, page_size: int = 20) -> dict:
        if status_filter and status_col is not None:
            query = query.filter(status_col == status_filter)
        total = query.count()
        items = query.order_by(order_col.desc()) \
                      .offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "items": items}
"""
基础设施模块 — 用户/角色/组织 业务服务层
===========================================
所有基础设施相关的业务逻辑在这里实现。

核心职责:
  1. 用户认证      — 登录验证（bcrypt 密码校验 + JWT 签发）
  2. 用户管理      — CRUD（创建/查询/更新，含逻辑外键校验）
  3. 角色查询      — 角色列表（用于前端下拉菜单、权限判断）
  4. 组织架构管理  — 组织树查询 + 创建节点

无物理外键策略（对应 API 文档第 14 章）:
  - 创建用户时: 如果传了 role_id，必须校验 sys_role 中存在该角色
  - 创建组织时: 如果传了 parent_id，必须校验 sys_organization 中存在父节点
  - 所有校验在 Service 层完成，数据库层面不做 FOREIGN KEY 约束

事务边界（对应 API 文档第 14.5 节）:
  - 写操作使用 with db.begin() 确保原子性
  - 事务内不调用外部 API（Dify、邮件等）

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》
  - 第 4 章   认证与鉴权接口
  - 第 14 章  应用层数据一致性保障
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

# --- 公共基础 ---
from models.common import (
    AuthError,
    ConflictError,
    NotFoundError,
    ReferenceNotFoundError,
    ValidationError,
    create_access_token,
    hash_password,
    verify_password,
)

# --- 数据模型 ---
from models.user import SysOrganization, SysRole, SysUser

# --- Schema ---
from schemas import PaginationParams
from schemas.student import (
    OrganizationCreate,
    OrganizationResponse,
    RoleResponse,
    TokenResponse,
    UserCreate,
    UserMeResponse,
    UserResponse,
    UserUpdate,
)


# ============================================================
# 一、用户认证
# ============================================================

def authenticate_user(db: Session, username: str, password: str) -> TokenResponse:
    """
    验证用户登录并签发 JWT Token。

    对应 API 文档第 4.2 节 POST /api/v1/auth/login。

    流程:
      1. 按 username 查 sys_user 表
      2. bcrypt 校验密码
      3. 检查账号状态（disabled 不允许登录）
      4. 签发 JWT Token 并返回用户信息

    参数:
        db:       数据库会话
        username: 登录账号
        password: 明文密码

    返回:
        TokenResponse（user_id + username + real_name + user_type + access_token）

    异常:
        40103: 用户名或密码错误（不区分具体原因，防止撞库枚举）
        40103: 账号已被禁用
    """
    # 1. 查用户（只用 username 查，因为 uk_username 唯一索引）
    user = db.query(SysUser).filter_by(username=username).first()

    # 2. 锁定检查（对应 API 文档 §4.2 规则4：连续 5 次失败锁定 30 分钟）
    if user and user.locked_until:
        now = datetime.now()
        if user.locked_until > now:
            remaining = int((user.locked_until - now).total_seconds() // 60) + 1
            raise AuthError(f"账户已锁定，请 {remaining} 分钟后重试")

    # 3. 用户名或密码错误 — 不告知具体是哪个错了（安全性：防撞库枚举）
    if user is None or not verify_password(password, user.password_hash):
        # 记录失败次数（用户存在时才记录）
        if user is not None:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= 5:
                user.locked_until = datetime.now() + timedelta(minutes=30)
            db.commit()
        raise AuthError("用户名或密码错误")

    # 4. 账号状态检查
    if user.status == "disabled":
        raise AuthError("账号已被禁用，请联系管理员")

    # 5. 签发 Token
    from config import ACCESS_TOKEN_EXPIRE_MINUTES

    token = create_access_token(
        user_id=user.id,
        username=user.username,
        user_type=user.user_type,
        role_id=user.role_id,
    )

    # 6. 登录成功后：重置登录失败计数 + 清除锁定 + 更新最后登录时间
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    # 7. 返回 Token + 用户信息
    return TokenResponse(
        user_id=user.id,
        username=user.username,
        real_name=user.real_name,
        user_type=user.user_type,
        role_id=user.role_id,
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 分钟 → 秒
    )


def get_current_user_info(db: Session, current_user: SysUser) -> UserMeResponse:
    """
    获取当前登录用户的详细信息。

    对应 API 文档第 4.3 节 GET /api/v1/auth/me。

    参数:
        db:           数据库会话
        current_user: 当前登录用户（由 get_current_user 依赖注入获得）

    返回:
        UserMeResponse，字段对齐 sys_user 表
    """
    return UserMeResponse(
        user_id=current_user.id,
        username=current_user.username,
        real_name=current_user.real_name,
        user_type=current_user.user_type,
        department=current_user.department,
        contact_info=current_user.contact_info,
        avatar_url=current_user.avatar_url,
        status=current_user.status,
    )


# ============================================================
# 二、用户管理 CRUD
# ============================================================


def create_user(db: Session, data: UserCreate) -> SysUser:
    """
    创建新用户。

    业务规则:
      1. username 唯一（uk_username 唯一索引兜底）
      2. 如果传了 role_id，校验 sys_role 记录存在（无物理外键策略）
      3. 密码用 bcrypt 哈希后存储

    参数:
        db:   数据库会话
        data: 用户创建请求体

    返回:
        新创建的 SysUser ORM 对象
    """
    # 1. 校验用户名唯一
    existing = db.query(SysUser).filter_by(username=data.username).first()
    if existing:
        raise ConflictError(f"用户名已存在: {data.username}")

    # 2. ⭐ 逻辑外键校验：如果传了 role_id，确认角色存在
    if data.role_id is not None:
        role = db.query(SysRole).filter_by(id=data.role_id).first()
        if not role:
            raise ReferenceNotFoundError("角色", data.role_id)

    # 3. 创建用户（密码 bcrypt 哈希）
    user = SysUser(
        username=data.username,
        password_hash=hash_password(data.password),  # 明文 → bcrypt 哈希
        real_name=data.real_name,
        user_type=data.user_type,
        role_id=data.role_id,
        department=data.department,
        contact_info=data.contact_info,
        avatar_url=data.avatar_url,
        status="normal",  # 新建用户默认状态 = normal
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def get_user(db: Session, user_id: int) -> SysUser:
    """
    根据 ID 查询单个用户。

    参数:
        db:      数据库会话
        user_id: 用户主键

    返回:
        SysUser ORM 对象

    异常:
        NotFoundError: 用户不存在
    """
    user = db.query(SysUser).filter_by(id=user_id).first()
    if not user:
        raise NotFoundError(f"用户不存在: id={user_id}")
    return user


def list_users(
    db: Session,
    pagination: PaginationParams,
    user_type: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    分页查询用户列表。

    支持筛选:
      - user_type: 按用户类型过滤（student / employee / admin）
      - keyword:   模糊搜索（匹配 username 或 real_name）
      - status:    按状态过滤（normal / disabled）

    参数:
        db:         数据库会话
        pagination: 分页参数（page, page_size）
        user_type:  用户类型筛选
        keyword:    关键词搜索
        status:     状态筛选

    返回:
        {items: [...], total: int, page: int, page_size: int}
    """
    # 构建基础查询
    query = db.query(SysUser)

    # 应用可选筛选条件（动态构建 WHERE 子句）
    if user_type:
        query = query.filter(SysUser.user_type == user_type)
    if status:
        query = query.filter(SysUser.status == status)
    if keyword:
        # LIKE 模糊搜索：匹配 username 或 real_name
        like_pattern = f"%{keyword}%"
        from sqlalchemy import or_

        query = query.filter(
            or_(
                SysUser.username.like(like_pattern),
                SysUser.real_name.like(like_pattern),
            )
        )

    # 总数（在分页前查询，不受 LIMIT/OFFSET 影响）
    total = query.count()

    # 分页 + 排序（按创建时间倒序，最新的在前）
    users = (
        query.order_by(SysUser.create_time.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
        .all()
    )

    # 转成 Pydantic Schema 列表（不直接返回 ORM 对象，解耦前端与数据库结构）
    items = [UserResponse.model_validate(u).model_dump() for u in users]

    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


def update_user(db: Session, user_id: int, data: UserUpdate) -> SysUser:
    """
    更新用户信息（部分更新 — 只修改传入的字段）。

    业务规则:
      1. 只更新 data 中非 None 的字段（部分更新语义）
      2. 如果传了 role_id，校验角色存在（无物理外键策略）
      3. 不在此接口中修改密码（密码修改走专门的 change_password）

    参数:
        db:      数据库会话
        user_id: 用户主键
        data:    用户更新请求体（只含需修改的字段）

    返回:
        更新后的 SysUser ORM 对象
    """
    # 1. 查用户
    user = get_user(db, user_id)

    # 2. ⭐ 逻辑外键校验：如果传了 role_id，确认角色存在
    if data.role_id is not None:
        role = db.query(SysRole).filter_by(id=data.role_id).first()
        if not role:
            raise ReferenceNotFoundError("角色", data.role_id)

    # 3. 只更新非 None 字段（部分更新）
    update_data = data.model_dump(exclude_unset=True)  # exclude_unset=True: 只返回实际传入的字段
    for field, value in update_data.items():
        setattr(user, field, value)

    # 4. 提交事务
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# 三、角色查询
# ============================================================


def list_roles(db: Session) -> List[RoleResponse]:
    """
    查询所有启用的角色。

    角色数据量小（5 条），直接全量返回，不分页。
    未来如果角色数量增长，可加分页参数。

    返回:
        角色列表（仅 status=1 的启用角色）

    性能说明:
      角色列表适合缓存（应用启动时加载到内存）。
      见数据库文档第 13.3 节热点数据缓存策略。
    """
    roles = db.query(SysRole).filter_by(status=1).order_by(SysRole.id).all()
    return [RoleResponse.model_validate(r) for r in roles]


# ============================================================
# 四、组织架构管理
# ============================================================


def create_organization(db: Session, data: OrganizationCreate) -> SysOrganization:
    """
    创建组织节点。

    业务规则:
      1. 如果传了 parent_id，校验父节点存在（无物理外键策略）
      2. sort_order 默认 0

    参数:
        db:   数据库会话
        data: 组织创建请求体

    返回:
        新创建的 SysOrganization ORM 对象
    """
    # 1. ⭐ 逻辑外键校验：如果指定了父节点，确认父节点存在
    if data.parent_id is not None:
        parent = db.query(SysOrganization).filter_by(id=data.parent_id).first()
        if not parent:
            raise ReferenceNotFoundError("上级组织", data.parent_id)

    # 2. 创建组织节点
    org = SysOrganization(
        org_name=data.org_name,
        parent_id=data.parent_id,
        org_type=data.org_type,
        sort_order=data.sort_order,
        status=1,  # 新建组织默认启用
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    return org


def list_organizations_flat(db: Session) -> List[OrganizationResponse]:
    """
    平铺查询所有启用的组织节点。

    不分页（组织数量通常不大），用于前端下拉菜单或树形组件自行组装。

    返回:
        所有 status=1 的组织节点列表（平铺，不含 children）
    """
    orgs = (
        db.query(SysOrganization)
        .filter_by(status=1)
        .order_by(SysOrganization.sort_order, SysOrganization.id)
        .all()
    )
    return [OrganizationResponse.model_validate(o) for o in orgs]


def get_organization_tree(db: Session) -> List[OrganizationResponse]:
    """
    查询完整组织架构树（递归嵌套）。

    从根节点（parent_id IS NULL）开始，递归加载所有子节点。
    用于前端树形组件直接渲染，无需前端自行组装。

    算法:
      1. 查所有 status=1 的组织 → 全量加载到内存
      2. 从根节点开始 BFS/DFS 递归组装 children
      3. 返回树根列表

    为什么不全量查一次然后内存组装？
      组织数量通常在 100 以内，一次查询比 N+1 查询快几个数量级。

    返回:
        树形组织节点列表（根节点，children 递归嵌套）
    """
    # 1. 一次查询加载所有启用组织
    all_orgs = (
        db.query(SysOrganization)
        .filter_by(status=1)
        .order_by(SysOrganization.sort_order, SysOrganization.id)
        .all()
    )

    if not all_orgs:
        return []

    # 2. 构建 id → 节点的映射表（方便 O(1) 查找子节点）
    node_map: Dict[int, OrganizationResponse] = {}
    for org in all_orgs:
        node_map[org.id] = OrganizationResponse.model_validate(org)

    # 3. 组装树：遍历所有节点，挂到各自 parent 的 children 下
    roots: List[OrganizationResponse] = []
    for org in all_orgs:
        node = node_map[org.id]
        if org.parent_id is not None and org.parent_id in node_map:
            # 有父节点 → 挂到父节点的 children 列表
            parent_node = node_map[org.parent_id]
            parent_node.children.append(node)
        else:
            # 无父节点（或父节点已删除/禁用）→ 作为根节点
            roots.append(node)

    return roots


# ============================================================
# 六、密码修改
# ============================================================


def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> None:
    """
    修改用户密码。

    业务流程:
      1. 查用户
      2. 验证旧密码（防止未授权修改）
      3. bcrypt 哈希新密码 → 更新入库

    参数:
        db:          数据库会话
        user_id:     要修改密码的用户 ID
        old_password: 当前密码（用于身份验证）
        new_password: 新密码
    """
    user = db.query(SysUser).filter_by(id=user_id).first()
    if not user:
        raise NotFoundError(f"用户不存在: id={user_id}")

    if not verify_password(old_password, user.password_hash):
        raise AuthError("旧密码错误")

    user.password_hash = hash_password(new_password)
    db.commit()


# ============================================================
# 五、种子数据初始化
# ============================================================


def seed_data(db: Session) -> None:
    """
    应用启动时自动初始化种子数据（仅当表为空时才插入，已有数据则跳过）。

    对应数据库设计文档第 11 章：
      - sys_role:  5 条角色（admin/employee/manager/team_leader/student）
      - sys_user:  1 个管理员（admin / admin123）

    设计要点:
      使用了"先查后插"的幂等逻辑——每次启动都调用，但只有表为空时才插入。
      这样不会因重复启动而创建重复数据。

    测试用户（文档第 11.4 节）：
      admin     / admin123  — 系统管理员
      employee1 / emp123    — 普通员工（后续按需添加）
      student1  / stu123    — 在读学生（后续按需添加）
    """
    # --- 1. 角色种子数据 ---
    if db.query(SysRole).count() == 0:
        roles = [
            SysRole(
                role_code="admin",
                role_name="系统管理员",
                description="最高权限，可管理所有模块和用户",
            ),
            SysRole(
                role_code="employee",
                role_name="员工",
                description="普通员工，可管理自己负责的客户",
            ),
            SysRole(
                role_code="manager",
                role_name="部门经理",
                description="管理人员，可查看本部门数据",
            ),
            SysRole(
                role_code="team_leader",
                role_name="班主任",
                description="学生班主任，负责学生请假审批和心理预警跟进",
            ),
            SysRole(
                role_code="student",
                role_name="学生",
                description="在校学生，可查看课程、提交请假和投诉",
            ),
        ]
        db.add_all(roles)
        db.commit()
        # 让 SQLAlchemy 知道这些对象已经有 id 了（后续可用 role.id）
        for r in roles:
            db.refresh(r)

    # --- 2. 管理员用户种子数据 ---
    if db.query(SysUser).filter_by(username="admin").count() == 0:
        # 找到 admin 角色
        admin_role = db.query(SysRole).filter_by(role_code="admin").first()
        admin = SysUser(
            username="admin",
            password_hash=hash_password("admin123"),
            real_name="系统管理员",
            user_type="admin",
            role_id=admin_role.id if admin_role else None,
            department="技术部",
            contact_info="admin@example.com",
            status="normal",
        )
        db.add(admin)
        db.commit()
