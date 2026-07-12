"""
学生智能助手 — 多轮对话接口

纯 Python + LLM（通义千问）实现：
  ① LLM 意图识别 + 槽位提取 → ② 槽位管理 → ③ 信息不完整追问 / 完整则执行业务 → ④ LLM 生成回复

用法:
  POST /api/v1/student/chat?student_id=1&message=我想请假
"""
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from config import DASHSCOPE_API_KEY, LLM_MODEL
from utils.database import get_db
from utils.llm_client import LLMClient
from services.student_service import StudentService

router = APIRouter(prefix="/student", tags=["学生助手对话"])

# =============================================================================
# LLM 客户端（单例）
# =============================================================================

_llm = LLMClient(api_key=DASHSCOPE_API_KEY, model=LLM_MODEL)


# =============================================================================
# 意图配置
# =============================================================================

INTENT_META = {
    "leave_request": {
        "name": "请假申请",
        "slots": ["leave_type", "start_time", "end_time", "reason"],
        "execute": "_exec_leave",    # StudentService 方法引用
        "confirm_fmt": (
            "请假申请已提交 ✅\n"
            "类型：{leave_type}\n"
            "时间：{start_time} 至 {end_time}\n"
            "事由：{reason}\n"
            "等待班主任审批~"
        ),
    },
    "complaint_submit": {
        "name": "投诉反馈",
        "slots": ["ticket_type", "category", "complaint_content"],
        "execute": "_exec_feedback",
        "confirm_fmt": (
            "反馈已提交 📋\n"
            "类型：{ticket_type}\n"
            "分类：{category}\n"
            "我们会尽快处理并通知你~"
        ),
    },
    "application_progress": {
        "name": "申请进度",
        "slots": [],           # 无需槽位，直接查
        "execute": "_exec_applications",
        "confirm_fmt": None,   # 动态生成
    },
    "deadline_query": {
        "name": "DDL查询",
        "slots": ["deadline_days"],
        "execute": "_exec_deadlines",
        "confirm_fmt": None,
    },
    "score_query": {
        "name": "成绩查询",
        "slots": [],
        "execute": "_exec_scores",
        "confirm_fmt": None,
    },
    "notification_query": {
        "name": "通知查询",
        "slots": [],
        "execute": "_exec_notifications",
        "confirm_fmt": None,
    },
    "upselling": {
        "name": "增值转化",
        "slots": [],
        "execute": "_exec_upselling",
        "confirm_fmt": None,
    },
    "psych_express": {
        "name": "心情表达",
        "slots": [],
        "execute": None,        # 纯 LLM 回复，不写库
        "confirm_fmt": None,
    },
    "chat": {
        "name": "闲聊",
        "slots": [],
        "execute": None,
        "confirm_fmt": None,
    },
}


# =============================================================================
# 对话状态
# =============================================================================

@dataclass
class ConversationState:
    student_id: int
    current_intent: str = ""
    filled: dict = field(default_factory=dict)      # 已填充槽位
    missing: list = field(default_factory=list)      # 待填充槽位
    confirm_pending: bool = False                     # 等用户确认
    history: list = field(default_factory=list)       # 消息历史 [{role,content}]
    last_active: datetime = field(default_factory=datetime.now)

    def expired(self) -> bool:
        return (datetime.now() - self.last_active).seconds > 300

    def reset(self, intent: str):
        self.current_intent = intent
        self.filled = {}
        self.missing = list(INTENT_META[intent]["slots"])
        self.confirm_pending = False

    def add_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > 20:
            self.history = self.history[-20:]


# 内存存储
_store: dict[int, ConversationState] = {}
_lock = threading.Lock()


# =============================================================================
# API 端点
# =============================================================================

@router.post("/chat")
def student_chat(
    student_id: int = Query(..., gt=0, description="学生ID"),
    message: str = Query(..., min_length=1, description="用户消息"),
    db: Session = Depends(get_db),
):
    svc = StudentService(db)

    # ---- 获取或创建对话状态 ----
    with _lock:
        s = _store.get(student_id)
        if s is None or s.expired():
            s = ConversationState(student_id=student_id)
            _store[student_id] = s
        s.last_active = datetime.now()
        s.add_history("user", message)

    # ---- 处理确认/取消提交 ----
    if s.confirm_pending:
        with _lock:
            s.confirm_pending = False
        if _is_confirm(message):
            return _do_execute(s, svc)
        elif _is_cancel(message):
            s.reset(s.current_intent)
            return _ok("好的，已取消。你想做什么？")
        # 不是确认/取消 → 当新消息继续

    # ---- 意图识别 ----
    intent = _llm.classify_intent(message, s.history[-10:])
    intent_name = intent.get("intent", "chat")
    confidence = intent.get("confidence", 0.3)
    slots_from_llm = intent.get("slots", {}) or {}

    # ---- 关键词兜底（LLM 调用失败/低置信度时） ----
    if confidence < 0.5 or intent_name == "chat":
        kw_intent, kw_slots = _keyword_detect(message)
        if kw_intent:
            intent_name = kw_intent
            slots_from_llm = {**slots_from_llm, **kw_slots}

    # ---- 闲聊 / 心情：直接 LLM 回复 ----
    if intent_name in ("chat", "psych_express"):
        reply = _gen_chat_or_psych(intent_name, message, s.history)
        s.add_history("assistant", reply)
        return _ok(reply)

    # ---- 申请/DDL/通知/成绩：直接执行，模板格式化回复（不用 LLM，防幻觉） ----
    if intent_name in ("application_progress", "deadline_query", "notification_query", "score_query", "upselling"):
        result = _exec_immediate(svc, intent_name, student_id, slots_from_llm)
        reply = _format_result(intent_name, result)
        s.add_history("assistant", reply)
        return _ok(reply)

    # ---- 请假/投诉：需要槽位收集 ----
    if intent_name != s.current_intent:
        s.reset(intent_name)

    # 填入 LLM 提取的槽位
    _merge_slots(s, slots_from_llm)

    if not s.missing:
        # 信息完整 → 回显确认
        s.confirm_pending = True
        cfg = INTENT_META[intent_name]
        reply = cfg["confirm_fmt"].format(**s.filled)
        reply += "\n\n确认提交吗？回复「确认」或「取消」"
        s.add_history("assistant", reply)
        return _ok(reply)

    # 信息不完整 → LLM 追问
    next_slot = s.missing[0]
    reply = _llm.ask_follow_up(
        next_slot, INTENT_META[intent_name]["name"], s.history[-10:]
    )
    if not reply:
        # LLM 挂了，用模板兜底
        asks = {
            "leave_type": "是什么类型的请假？病假 / 事假 / 紧急？",
            "start_time": "从什么时候开始？",
            "end_time": "到什么时候结束？",
            "reason": "能说一下原因吗？",
            "ticket_type": "是投诉、建议还是咨询？",
            "category": "关于哪方面？签证/院校/生活/教学/其他？",
            "complaint_content": "能详细说说吗？",
            "deadline_days": "查未来几天的DDL？默认30天",
        }
        reply = asks.get(next_slot, f"请补充一下{next_slot}？")
    s.add_history("assistant", reply)
    return _ok(reply)


# =============================================================================
# 执行方法（调 StudentService）
# =============================================================================

def _do_execute(s: ConversationState, svc: StudentService) -> dict:
    """确认后执行业务（LLM 返回中文，需映射为英文 Enum）"""
    intent = s.current_intent
    from schemas.student import LeaveCreate, FeedbackCreate

    # 中文 → 英文映射
    LEAVE_TYPE_MAP = {"病假": "sick", "事假": "personal", "紧急": "emergency",
                       "sick": "sick", "personal": "personal", "emergency": "emergency"}
    TICKET_TYPE_MAP = {"投诉": "complaint", "建议": "suggestion", "咨询": "consult",
                        "complaint": "complaint", "suggestion": "suggestion", "consult": "consult"}

    if intent == "leave_request":
        raw_type = s.filled.get("leave_type", "sick").strip()
        leave_type = LEAVE_TYPE_MAP.get(raw_type, "sick")
        body = LeaveCreate(
            student_id=s.student_id,
            service_type="leave",
            leave_type=leave_type,
            start_time=_pad_time(s.filled.get("start_time", "")),
            end_time=_pad_time(s.filled.get("end_time", "")),
            reason=s.filled.get("reason", "未知"),
        )
        leave = svc.create_leave_request(body)
        r = {"success": True, "id": leave.id, "status": leave.status}
        reply = _llm.generate_result_reply("请假申请", r, s.history[-10:])
        s.history.clear()  # 执行完毕，重置对话
        s.reset(intent)
        return _ok(reply or s.filled.get("confirm", "已提交 ✅"))

    if intent == "complaint_submit":
        raw_tt = s.filled.get("ticket_type", "complaint").strip()
        raw_cat = s.filled.get("category", "其他").strip()
        body = FeedbackCreate(
            student_id=s.student_id,
            ticket_type=TICKET_TYPE_MAP.get(raw_tt, "complaint"),
            category=raw_cat,
            content=s.filled.get("complaint_content", " "),
        )
        ticket = svc.create_feedback(body)
        r = {"success": True, "id": ticket.id, "status": ticket.status}
        reply = _llm.generate_result_reply("投诉反馈", r, s.history[-10:])
        s.history.clear()
        s.reset(intent)
        return _ok(reply or "已提交 📋")

    return _ok("已完成")


def _exec_immediate(svc: StudentService, intent: str, student_id: int, slots: dict) -> dict:
    """无需槽位收集，直接执行"""
    if intent == "application_progress":
        result = svc.list_applications(student_id)
        items = result.get("items", [])
        return {
            "success": True,
            "count": len(items),
            "items": [
                {"school": i.target_school, "major": i.target_major,
                 "stage": i.stage, "deadline": str(i.deadline)}
                for i in items[:5]
            ],
        }
    if intent == "deadline_query":
        days = int(slots.get("deadline_days", 30) or 30)
        result = svc.list_deadlines(student_id, upcoming_days=days)
        items = result.get("items", [])
        return {
            "success": True,
            "count": len(items),
            "items": [
                {"title": d.title, "deadline": str(d.deadline),
                 "status": d.status, "type": d.deadline_type}
                for d in items[:10]
            ],
        }
    if intent == "score_query":
        result = svc.list_scores(student_id)
        items = result.get("items", [])
        return {
            "success": True,
            "count": len(items),
            "items": [
                {"course": s.course_name, "score": float(s.score) if s.score else None,
                 "semester": s.semester, "credit": float(s.credit) if s.credit else None}
                for s in items[:10]
            ],
        }
    if intent == "upselling":
        from schemas.student import IntentCreate
        body = IntentCreate(
            student_id=student_id,
            intent_type="other",
            intent_name=slots.get("course_interest", "") or "学生表达升学意向",
            source="chat", remark="",
        )
        try:
            svc.create_intent(body)
        except Exception:
            pass  # 意向记录失败不阻塞对话
        recs = svc.get_recommendations(student_id)
        return {"success": True, "recommendations": recs.get("items", []) if isinstance(recs, dict) else []}
    if intent == "notification_query":
        result = svc.list_notifications(student_id)
        items = result.get("items", [])
        return {
            "success": True,
            "count": len(items),
            "unread": result.get("unread_count", 0),
            "items": [
                {"title": n.title, "content": n.content, "is_read": n.is_read}
                for n in items[:5]
            ],
        }
    return {"success": False, "error": "未知意图"}


# =============================================================================
# 辅助函数
# =============================================================================

_KEYWORDS = {
    "leave_request": ["请假", "病假", "事假", "休息", "不舒服", "感冒", "发烧",
                       "头疼", "肚子疼", "家里有事", "想请", "请个假"],
    "complaint_submit": ["投诉", "太慢", "不满", "差劲", "反馈", "建议", "坑",
                          "等了很久", "还没处理", "什么情况"],
    "application_progress": ["申请", "offer", "录取", "进度", "审核", "院校"],
    "deadline_query": ["DDL", "截止", "deadline", "考试", "论文", "提交日期"],
    "score_query": ["成绩", "分数", "考试分数", "GPA", "绩点", "多少分", "考了多少",
                     "我的成绩", "查成绩", "查下成绩", "成绩单", "各科成绩",
                     "成绩怎么样", "成绩是多少", "考得怎么样", "分数多少", "排名"],
    "notification_query": ["通知", "消息", "提醒", "小红点"],
    "upselling": [
        "读博", "读硕", "读研", "博士", "硕士", "研究生",
        "升学", "提升学历", "继续读", "继续学", "深造", "进修",
        "硕博连读", "博士申请", "硕士申请", "申博", "申硕",
        "想读", "想考", "想申请", "想继续读",
        "学历提升", "背景提升", "PhD", "Master",
        "再读一个", "还想读", "有没有博士项目",
    ],
    "psych_express": ["压力", "焦虑", "难过", "失眠", "想家", "累", "崩溃", "心情"],
}
_SLOT_HINTS = {
    "leave_type": {"病假": "sick", "sick": "sick", "事假": "personal",
                    "personal": "personal", "急": "emergency", "紧急": "emergency"},
    "ticket_type": {"投诉": "complaint", "建议": "suggestion", "咨询": "consult"},
}


def _keyword_detect(msg: str) -> tuple:
    """关键词兜底检测，返回 (intent, slots)"""
    scores = {}
    for intent, kws in _KEYWORDS.items():
        score = sum(1 for kw in kws if kw in msg)
        if score > 0:
            scores[intent] = score
    if not scores:
        return (None, {})

    best = max(scores, key=scores.get)
    slots = {}

    # 疾病症状 → 自动填 leave_type=sick
    sick_words = ["感冒", "发烧", "头疼", "肚子疼", "不舒服", "生病", "咳嗽", "喉咙痛"]
    if best == "leave_request" and any(w in msg for w in sick_words):
        slots["leave_type"] = "sick"
    for slot, mapping in _SLOT_HINTS.items():
        for kw, val in mapping.items():
            if kw in msg:
                slots[slot] = val
                break
    return (best, slots)


def _format_result(intent: str, result: dict) -> str:
    """模板格式化查询结果，不调 LLM，杜绝幻觉"""
    items = result.get("items", [])
    count = result.get("count", 0)

    if intent == "score_query":
        if not items:
            return "暂无成绩记录 📚\n可能是还没录入，联系班主任确认一下~"
        lines = ["你的成绩如下 📊\n"]
        for s in items:
            sc = f"{s.get('score', '-')}分" if s.get('score') is not None else "-"
            lines.append(f"  · {s.get('course','')}  {sc}  ({s.get('semester','')})")
        return "\n".join(lines)

    if intent == "upselling":
        recs = result.get("recommendations", [])
        if not recs:
            return "已经记录你的升学意向 📝\n目前暂无匹配的推荐项目，我们会尽快为你匹配~"
        lines = ["根据你的意向，推荐以下项目 🎓\n"]
        for r in recs[:3]:
            name = r.get("project_name", r.get("name", ""))
            desc = r.get("description", r.get("desc", ""))
            lines.append(f"  · {name}")
            if desc:
                lines.append(f"    {desc[:60]}")
        lines.append("\n需要详细了解可以预约顾问老师~")
        return "\n".join(lines)

    if intent == "application_progress":
        if not items:
            return "暂无申请记录 🎓\n需要帮你了解申请流程吗？"
        lines = ["你的留学申请进度 🎓\n"]
        for a in items:
            stage = {"document_prep": "📝材料准备", "submitted": "📤已提交",
                     "under_review": "🔍审核中", "offer_received": "🎉已录取",
                     "visa_processing": "🛂签证中", "enrolled": "✅已入学"}
            s = stage.get(a.get("stage", ""), a.get("stage", "处理中"))
            deadline = f"，截止：{a.get('deadline','')}" if a.get("deadline") else ""
            lines.append(f"  · {a.get('school','')} {a.get('major','')} → {s}{deadline}")
        return "\n".join(lines)

    if intent == "deadline_query":
        if not items:
            return "近期没有快到期的DDL 🎉\n继续保持~"
        lines = ["近期 DDL 提醒 ⏰\n"]
        for d in items:
            status_icon = {"pending": "⏳", "reminded": "🔔", "done": "✅", "missed": "❌"}
            icon = status_icon.get(d.get("status", ""), "")
            lines.append(f"  {icon} {d.get('title','')} — 截止：{d.get('deadline','')}")
        return "\n".join(lines)

    if intent == "notification_query":
        unread = result.get("unread", 0)
        if not items:
            return "暂时没有新消息~"
        lines = [f"你有 {unread} 条未读消息 🔔\n"]
        for n in items[:5]:
            status = "🔵" if not n.get("is_read") else "⚪"
            lines.append(f"  {status} {n.get('title','')}")
        if count > 5:
            lines.append(f"\n...还有 {count - 5} 条消息")
        return "\n".join(lines)

    return f"查询完成，共 {count} 条"


def _merge_slots(s: ConversationState, slots: dict):
    """将 LLM 提取的槽位填入 filled，从 missing 移除"""
    for key in list(s.missing):
        val = slots.get(key)
        if val and val != "空" and str(val).strip():
            s.filled[key] = str(val).strip()
            s.missing.remove(key)


def _gen_chat_or_psych(intent: str, message: str, history: list) -> str:
    """闲聊或心情表达的 LLM 回复"""
    if intent == "psych_express":
        return _llm.generate_chat_reply(
            f"学生说：{message}\n请共情回应，不超过50字。", history
        )
    return _llm.generate_chat_reply(message, history)


def _pad_time(val: str) -> str:
    """确保时间格式符合 YYYY-MM-DD HH:mm，'明天' → 具体日期"""
    val = val.strip()
    if not val:
        return ""
    # 已经是标准格式
    if len(val) >= 16 and "T" not in val:
        return val[:16] if len(val) >= 16 else val
    # LLM 可能返回的相对时间或错误格式
    try:
        from datetime import datetime
        dt = datetime.strptime(val[:16], "%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    # 最终兜底
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 08:00")


def _is_confirm(msg: str) -> bool:
    return any(w in msg for w in ["确认提交", "确认", "提交吧", "提交申请", "好的提交", "OK提交"])


def _is_cancel(msg: str) -> bool:
    return any(w in msg for w in ["取消", "算了", "不要", "不了", "不用", "别"])


def _ok(data) -> dict:
    return {"code": 0, "message": "success", "data": data}
