"""
CRM 业务逻辑服务
负责：意向客户 CRUD、状态流转校验、跟进记录管理
员工日报业务逻辑服务
负责：日报提交、查询、汇总统计
"""
import json
import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_, update, func, text

from config import LLM_API_KEY, LLM_API_URL, LLM_MODEL, LLM_TIMEOUT
from models.crm import (
    CrmLead, CrmFollowUp, EmployeeDailyReport,
    AssistantMessage, AssistantSession,
)
from schemas.crm import (
    LeadCreate, LeadUpdate, LeadStatusUpdate,
    LeadListResponse,
    FollowUpCreate,
    DailyReportCreate,
    DailyReportManagementSummary,
    EmployeeSummaryItem, LeadResponse,
    AssistantChatRequest, AssistantChatResponse,
    AssistantMessageResponse, AssistantSessionResponse,
)

logger = logging.getLogger(__name__)

# SysUser 模型可能尚未创建，做容错导入
try:
    from models.user import SysUser
    HAS_SYS_USER = True
except ImportError:
    HAS_SYS_USER = False


# ==================== 业务异常类（对齐 API 规范 V1.2 第 3 章错误码） ====================

class BizError(Exception):
    """业务异常基类，router 层统一捕获并转为 JSON 错误响应"""
    def __init__(self, code: int, message: str, status_code: int = 400):
        self.code = code
        # 业务错误码，如 40001、40401，前端可根据此码做不同处理
        self.message = message
        # HTTP 状态码，由 exception_handler 读取并设置到响应上
        self.status_code = status_code
        super().__init__(message)
        # 调用 Exception.__init__，保留标准异常的堆栈跟踪能力


class ParamError(BizError):
    """参数校验失败 40001"""
    def __init__(self, message: str):
        super().__init__(code=40001, message=message, status_code=400)
        # 40001 = 请求参数不合法，前端可直接展示 message 给用户


class NotFoundError(BizError):
    """资源不存在 40401"""
    def __init__(self, message: str):
        super().__init__(code=40401, message=message, status_code=404)
        # 40401 = 请求的资源（客户/日报/跟进记录）不存在


class RefNotFoundError(BizError):
    """关联实体不存在 40402"""
    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404
        )
        # 40402 = 逻辑外键校验失败，如 owner_employee_id 对应的员工不存在


class StateError(BizError):
    """状态不允许操作 40902 / 42204"""
    def __init__(self, message: str, code: int = 40902):
        super().__init__(code=code, message=message, status_code=422)
        # 42204 = 状态流转不合法（如从终态 signed 回退）


class ConflictError(BizError):
    """业务冲突 40901"""
    def __init__(self, message: str):
        super().__init__(code=40901, message=message, status_code=409)
        # 40901 = 并发冲突或重复提交（如同一员工同日重复提交日报）


# 客户状态流转规则：signed 和 lost 是终态，不可回退
VALID_STATUS_TRANSITIONS = {
    "new": ["contacting", "lost"],
    "contacting": ["qualified", "lost"],
    "qualified": ["signed", "lost"],
    "signed": [],       # 终态：已签约，不允许任何状态变更
    "lost": [],          # 终态：已流失，不允许任何状态变更
}
# 用途：update_lead_status() 中校验状态流转合法性
# 扩展：新增状态时只需在此字典中添加对应的允许目标状态列表


# ==================== LLM 辅助（共享工具，原 assistant_service 下沉） ====================

def _call_llm(system_prompt: str, user_content: str) -> Optional[str]:
    """调用 LLM Chat Completions API（同步阻塞）；未配置/失败返回 None。"""
    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY 未配置，跳过 LLM 调用")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 包未安装，请执行: pip install openai>=1.30.0")
        return None
    try:
        import httpx
        # trust_env=False: 避免继承 Windows 系统代理导致 HTTPS TLS 握手失败
        _http_client = httpx.Client(timeout=LLM_TIMEOUT, trust_env=False)
        client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_API_URL,
            timeout=LLM_TIMEOUT,
            http_client=_http_client,
        )
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content
        logger.info(f"LLM 调用成功: model={LLM_MODEL}")
        return content
    except Exception as e:
        logger.error(f"LLM 调用失败: {type(e).__name__}: {e}")
        return None


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 返回文本中提取 JSON 对象（兼容 markdown 包裹/尾逗号）。"""
    if not text or not text.strip():
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.replace("```", "")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        fixed = re.sub(r",\s*}", "}", json_str)
        fixed = re.sub(r",\s*]", "]", fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
    logger.warning("无法从 LLM 输出中提取 JSON")
    return None


def is_llm_available() -> bool:
    """检查 LLM 服务是否可用（仅检查配置，不发起网络请求）。"""
    if not LLM_API_KEY:
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def _crm_llm_text(system_prompt: str, user_content: str) -> Optional[str]:
    """调用大模型返回纯文本；未配置/失败返回 None（优雅降级，不抛错打断主流程）"""
    try:
        return _call_llm(system_prompt, user_content)
    except Exception:
        return None


def _crm_llm_json(system_prompt: str, user_content: str) -> Optional[dict]:
    """调用大模型并解析 JSON；失败/格式错误返回 None"""
    raw = _crm_llm_text(system_prompt, user_content)
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class CrmService:
    """意向客户 & 跟进记录 业务逻辑"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== 意向客户 CRUD ====================

    def create_lead(self, data: LeadCreate) -> CrmLead:
        """
        新增意向客户

        业务规则：
        - customer_name 必填
        - 新客户默认状态 new
        - owner_employee_id 默认为当前登录用户（当前版本: 从请求体获取）
        - 插入前校验 owner_employee_id 对应的 sys_user 存在且 user_type='employee'
        """
        owner_id = data.owner_employee_id

        # 逻辑外键校验：校验负责人存在且为员工
        if owner_id is not None and HAS_SYS_USER:
            owner = self.db.query(SysUser).filter(
                SysUser.id == owner_id,
                SysUser.user_type == 'employee',
                SysUser.status == 'normal'
            ).first()
            # 三个条件：ID存在 + 用户类型为员工 + 账号正常，任一不满足则拒绝
        if not owner:
            raise RefNotFoundError("员工", owner_id)

        # LLM 结构化提取（替代外部 Dify）：用 raw_content 回填未提供的字段
        if getattr(data, "raw_content", None):
            extracted = self._llm_extract_lead_fields(data.raw_content)
            if extracted:
                for f in ["gender", "age", "education_level", "intended_country",
                          "intended_major", "source_channel", "contact_info",
                          "background_info", "remark"]:
                    if not getattr(data, f, None) and extracted.get(f):
                        setattr(data, f, extracted.get(f))

        lead = CrmLead(
            status="new",
            **data.model_dump(exclude={"raw_content"})
            # **data.model_dump(mode="json") 展开所有 Pydantic 字段为关键字参数
            # 排除 raw_content：该字段仅用于 LLM 抽取，不是 crm_lead 表的列
        )
        self.db.add(lead)
        # 将新对象加入 SQLAlchemy 会话的待插入队列
        self.db.commit()
        # 提交事务，生成 INSERT SQL 并执行，此时 lead.id 被数据库自动赋值
        self.db.refresh(lead)
        # 刷新对象，从数据库重新加载（获取自增 ID、server_default 默认值等）
        return lead

    def _llm_extract_lead_fields(self, raw: str) -> Optional[dict]:
        """调用大模型从自然语言描述中抽取客户结构化字段（失败返回 None）"""
        system = (
            "你是留学咨询公司的客户信息抽取助手。从用户自然语言描述中抽取客户结构化字段。\n"
            "只返回 JSON（不要其他内容）：\n"
            "{\"customer_name\":\"姓名或空\",\"gender\":\"男/女/空\",\"age\":数字或空,"
            "\"education_level\":\"学历或空\",\"intended_country\":\"意向国家或空\","
            "\"intended_major\":\"意向专业或空\",\"source_channel\":\"来源渠道或空\","
            "\"contact_info\":\"联系方式或空\",\"background_info\":\"背景补充或空\","
            "\"remark\":\"备注或空\"}\n"
            "规则：只抽取文本中明确提到的信息，未提及的字段留空；不要编造。"
        )
        return _crm_llm_json(system, raw)

    def generate_lead_insight(self, lead_id: int) -> Optional[str]:
        """基于客户资料+跟进历史，调用 LLM 生成客户洞察与下一步建议"""
        lead = self.get_lead(lead_id)
        if not lead:
            return None
        follow_ups = self.list_follow_ups(lead_id)
        ctx = (
            f"客户姓名：{lead.customer_name}\n"
            f"状态：{lead.status}\n"
            f"意向国家：{lead.intended_country or '未知'}\n"
            f"意向专业：{lead.intended_major or '未知'}\n"
            f"学历：{lead.education_level or '未知'}\n"
            f"背景：{lead.background_info or '无'}\n"
            f"备注：{lead.remark or '无'}\n"
            f"跟进记录数：{len(follow_ups)}\n"
        )
        for fu in follow_ups[:10]:
            ctx += f"- [{fu.follow_type}] {fu.content}（下一步：{fu.next_plan or '无'}）\n"
        system = (
            "你是资深留学顾问。基于以下客户资料与跟进记录，生成一段简洁的客户洞察"
            "（当前阶段判断 + 核心诉求 + 下一步跟进建议）。150字以内，分点、专业、可落地。"
        )
        return _crm_llm_text(system, ctx)

    def summarize_leads(self, result: "LeadListResponse") -> Optional[str]:
        """对意向客户列表生成 LLM 摘要（可选 ai_summary 用）"""
        if not result or not result.items:
            return None
        lines = [
            f"- {it.customer_name}（{it.status}）："
            f"{it.intended_major or '未知专业'}，意向{it.intended_country or '未知'}"
            for it in result.items[:20]
        ]
        system = "你是销售主管助理。用 3-5 句话总结以下意向客户列表的整体情况（数量、阶段分布、重点机会）。"
        return _crm_llm_text(system, "\n".join(lines))

    def get_lead(self, lead_id: int) -> Optional[CrmLead]:
        """根据 ID 查询客户（排除已软删除的）"""
        return (
            self.db.query(CrmLead)
            .filter(CrmLead.id == lead_id)
            .first()
            # .first() 返回第一条匹配记录，无匹配则返回 None
        )

    def list_leads(
        self,
        status: Optional[str] = None,
        owner_employee_id: Optional[int] = None,
        keyword: Optional[str] = None,
        create_time_start: Optional[date] = None,
        create_time_end: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> LeadListResponse:
        """条件搜索 + 分页查询客户列表"""
        query = self.db.query(CrmLead)
        # 基础查询：意向客户列表

        if status:
            query = query.filter(CrmLead.status == status)
        if owner_employee_id:
            query = query.filter(CrmLead.owner_employee_id == owner_employee_id)
        if keyword:
            query = query.filter(
                or_(
                    CrmLead.customer_name.contains(keyword),
                    CrmLead.contact_info.contains(keyword),
                )
                # or_() = SQL 的 OR，姓名或联系方式任一匹配即返回
            )
        if create_time_start:
            query = query.filter(
                func.date(CrmLead.create_time) >= create_time_start
                # func.date() 提取 DATETIME 的日期部分，忽略时分秒
            )
        if create_time_end:
            query = query.filter(
                func.date(CrmLead.create_time) <= create_time_end
            )

        total = query.count()
        # 先 count 再分页：获取符合条件的总记录数（用于前端分页组件）
        items = (
            query.order_by(CrmLead.create_time.desc())
            .offset((page - 1) * page_size)
            # offset 跳过前 N 页的记录，page=1 时 offset=0
            .limit(page_size)
            # limit 限制每页条数
            .all()
        )

        return LeadListResponse(
            items=[LeadResponse.model_validate(item) for item in items],
            # model_validate：将 ORM 对象转为 Pydantic Schema，自动过滤未定义字段
            total=total,
            page=page,
            page_size=page_size,
        )

    def update_lead(self, lead_id: int, data: LeadUpdate) -> Optional[CrmLead]:
        """更新客户基本信息"""
        lead = self.get_lead(lead_id)
        if not lead:
            return None

        update_data = data.model_dump(exclude_unset=True)
        # exclude_unset=True：只导出客户端实际传了的字段，未传的字段不出现在 dict 中
        # 这样实现了"部分更新"：只修改传了的字段，未传的保持原值

        # 如果更新了 owner_employee_id，校验新负责人存在
        if "owner_employee_id" in update_data and HAS_SYS_USER:
            new_owner_id = update_data["owner_employee_id"]
            if new_owner_id is not None:
                owner = self.db.query(SysUser).filter(
                    SysUser.id == new_owner_id,
                    SysUser.user_type == 'employee',
                    SysUser.status == 'normal'
                ).first()
                if not owner:
                    raise RefNotFoundError("员工", new_owner_id)

        for key, value in update_data.items():
            setattr(lead, key, value)
            # 动态设置 ORM 对象属性，只修改 update_data 中有的字段

        # 若更新了 background_info，调用 LLM 重新抽取结构化标签回填空字段
        if update_data.get("background_info"):
            extracted = self._llm_extract_lead_fields(update_data["background_info"])
            if extracted:
                for f in ["gender", "age", "education_level", "intended_country",
                          "intended_major", "source_channel", "contact_info", "remark"]:
                    cur = getattr(lead, f, None)
                    if (cur is None or cur == "") and extracted.get(f):
                        setattr(lead, f, extracted.get(f))

        self.db.commit()
        # SQLAlchemy 自动追踪变更，只生成被修改字段的 UPDATE SET
        self.db.refresh(lead)
        return lead

    def update_lead_status(self, lead_id: int, data: LeadStatusUpdate) -> CrmLead:
        """
        更新客户状态（含业务规则校验 + 条件更新防并发）

        状态机：
        new → contacting → qualified → signed（终态）
          │       │           │
          └───────┴───────────┴──────────→ lost（终态，必须填 lost_reason）

        - signed 和 lost 是终态，不能再变更
        - lost 时必须填写 lost_reason
        - 使用条件 UPDATE 防并发状态覆盖
        """
        lead = self.get_lead(lead_id)
        if not lead:
            raise NotFoundError("客户不存在")

        current_status = lead.status
        new_status = data.status

        # 校验状态流转合法性
        allowed = VALID_STATUS_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise StateError(
                f"状态流转不合法：'{current_status}' → '{new_status}'。"
                f"允许的目标状态：{allowed if allowed else '无（当前为终态）'}",
                code=42204,
            )
        # 从 VALID_STATUS_TRANSITIONS 字典查询当前状态允许跳转到哪些状态

        # lost 时必须填写原因
        if new_status == "lost" and not data.lost_reason:
            raise ParamError("客户状态变更为 lost 时，必须填写 lost_reason")

        # 条件更新防并发：只有当前状态匹配时才更新
        values = {
            "status": new_status,
            "update_time": func.now(),
        }
        if new_status == "lost" and data.lost_reason:
            values["lost_reason"] = data.lost_reason

        result = self.db.execute(
            update(CrmLead)
            .where(
                CrmLead.id == lead_id,
                CrmLead.status == current_status,  # 乐观锁条件
            )
            # 条件 UPDATE：WHERE id=X AND status=current_status
            # 如果并发请求先改了状态，此处的 rowcount 将为 0
            .values(**values)
        )

        if result.rowcount == 0:
            raise ConflictError("状态已被其他操作修改，请刷新后重试")
        # rowcount=0 表示没有行被更新，说明 status 已被并发请求修改

        self.db.commit()
        self.db.refresh(lead)
        return lead

    def generate_status_suggestion(self, lead: "CrmLead", new_status: str) -> Optional[str]:
        """状态流转后调用 LLM 生成跟进/挽回建议"""
        ctx = (f"客户：{lead.customer_name}，状态刚变更为：{new_status}。"
               f"意向专业：{lead.intended_major or '未知'}，"
               f"意向国家：{lead.intended_country or '未知'}。")
        if new_status == "lost":
            system = "客户刚流失。给出 2-3 条流失挽回建议，简洁可执行，80字以内。"
        elif new_status == "signed":
            system = "客户刚签约。给出 2-3 条签约后跟进建议（如服务启动、转介绍），简洁可执行，80字以内。"
        else:
            system = "客户状态刚变更。给出 1-2 条下一步跟进建议，简洁可执行，60字以内。"
        return _crm_llm_text(system, ctx)

    # ==================== 跟进记录 ====================

    def create_follow_up(self, lead_id: int, data: FollowUpCreate) -> tuple[CrmFollowUp, Optional[str]]:
        """
        新增跟进记录

        业务规则：
        - lead_id 对应的 crm_lead 记录必须存在（应用层逻辑外键校验）
        - content 为必填
        - 同步更新 crm_lead.last_contact_time 和 update_time（在同一事务中）
        """
        # 逻辑外键校验：客户必须存在
        lead = self.get_lead(lead_id)
        if not lead:
            raise NotFoundError(f"意向客户不存在: id={lead_id}")

        # LLM 结构化（替代外部 Dify）：优先用 raw_content 生成 content / 建议 next_plan
        ai_next_plan = None
        if not data.content and data.raw_content:
            structured = self._llm_structure_follow_up(data.raw_content)
            if structured:
                data.content = structured.get("content") or data.raw_content
                ai_next_plan = structured.get("next_plan")
                if not data.next_plan and ai_next_plan:
                    data.next_plan = ai_next_plan
            else:
                data.content = data.raw_content
        if not data.content:
            raise ParamError("content 与 raw_content 至少提供一个")

        # 创建跟进记录
        follow_up = CrmFollowUp(lead_id=lead_id, **data.model_dump(exclude={"raw_content"}))
        # 排除 raw_content：该字段仅用于 LLM 抽取，不是 crm_follow_up 表的列
        self.db.add(follow_up)

        # 同步更新客户最后联系时间和更新时间（与跟进记录在同一事务中）
        self.db.execute(
            update(CrmLead)
            .where(CrmLead.id == lead_id)
            .values(
                last_contact_time=func.now(),
                update_time=func.now(),
            )
        )
        self.db.commit()

        self.db.refresh(follow_up)
        return follow_up, ai_next_plan

    def list_follow_ups(self, lead_id: int) -> List[CrmFollowUp]:
        """查询某客户的跟进历史（按时间倒序，排除已删除）"""
        return (
            self.db.query(CrmFollowUp)
            .filter(
                CrmFollowUp.lead_id == lead_id,
            )
            .order_by(CrmFollowUp.create_time.desc())
            .all()
        )

    def _llm_structure_follow_up(self, raw: str) -> Optional[dict]:
        """调用大模型将口述跟进整理为结构化 JSON"""
        system = (
            "你是销售跟进记录整理助手。将口述的跟进内容整理为结构化 JSON：\n"
            "{\"content\":\"整理后的跟进内容（简洁书面语）\","
            "\"next_plan\":\"下一步计划或空\"}\n只返回 JSON。"
        )
        return _crm_llm_json(system, raw)

    def summarize_follow_ups(self, lead_id: int) -> Optional[str]:
        """对某客户的跟进历史生成 LLM 摘要（可选 ai_summary 用）"""
        items = self.list_follow_ups(lead_id)
        if not items:
            return None
        lines = [
            f"- {fu.content}（方式：{fu.follow_type}，下一步：{fu.next_plan or '无'}）"
            for fu in items[:20]
        ]
        system = "你是销售助理。用 2-3 句话总结该客户的跟进历史与当前进展，80字以内。"
        return _crm_llm_text(system, "\n".join(lines))


class EmployeeService:
    """员工日报 业务逻辑"""

    def __init__(self, db: Session):
        self.db = db

    def create_report(self, data: DailyReportCreate) -> EmployeeDailyReport:
        """
        提交日报

        业务规则：
        - 同一员工同一天只能提交一条日报（唯一约束）
        - report_date 不能是未来日期
        - 校验 employee_id 对应的 sys_user 存在且 user_type='employee'
        """
        # 日期校验
        if data.report_date > date.today():
            raise ParamError("report_date 不能是未来日期")
        # 防止提交未来日期的日报，保证数据真实性

        # 逻辑外键校验：员工存在
        if HAS_SYS_USER:
            employee = self.db.query(SysUser).filter(
                SysUser.id == data.employee_id,
                SysUser.user_type == 'employee',
            ).first()
            if not employee:
                raise RefNotFoundError("员工", data.employee_id)

        # 检查是否已存在同日日报
        existing = (
            self.db.query(EmployeeDailyReport)
            .filter(
                EmployeeDailyReport.employee_id == data.employee_id,
                EmployeeDailyReport.report_date == data.report_date,
            )
            .first()
        )
        if existing:
            raise ConflictError(
                f"员工 {data.employee_id} 在 {data.report_date} 已提交过日报，"
                "如需修改请使用更新接口"
            )
        # 应用层检查：同一员工同一天只能有一份日报
        # 数据库层也有 uk_employee_date 唯一索引做兜底保护

        # LLM 结构化提取（替代外部 Dify）：将口述原文拆为结构化日报字段
        if data.raw_content:
            structured = self._llm_structure_report(data.raw_content)
            if structured:
                data.content = structured.get("content") or data.content or data.raw_content
                if not data.key_progress and structured.get("key_progress"):
                    data.key_progress = structured["key_progress"]
                if not data.risks and structured.get("risks"):
                    data.risks = structured["risks"]
                if not data.next_plan and structured.get("next_plan"):
                    data.next_plan = structured["next_plan"]
            elif not data.content:
                data.content = data.raw_content

        report = EmployeeDailyReport(**data.model_dump())
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def _llm_structure_report(self, raw: str) -> Optional[dict]:
        """调用大模型将口述日报原文整理为结构化 JSON"""
        system = (
            "你是员工日报整理助手。将口述的当日工作原文整理为结构化 JSON：\n"
            "{\"content\":\"整理后的日报正文（书面语）\","
            "\"key_progress\":[\"关键进展1\",\"关键进展2\"],"
            "\"risks\":[\"风险或阻塞1\"],"
            "\"next_plan\":\"下一步计划\"}\n"
            "规则：key_progress/risks 为字符串数组，没有则给空数组；只返回 JSON。"
        )
        return _crm_llm_json(system, raw)

    def summarize_reports(self, reports: List[EmployeeDailyReport]) -> Optional[str]:
        """对员工日报列表生成 LLM 摘要（可选 ai_summary 用）"""
        if not reports:
            return None
        lines = [
            f"- 员工{r.employee_id}：进展[{'、'.join(r.key_progress or []) or '无'}]；"
            f"风险[{'、'.join(r.risks or []) or '无'}]"
            for r in reports[:30]
        ]
        system = "你是团队主管助理。用 3-5 句话总结以下员工日报的整体进展、风险与重点，120字以内。"
        return _crm_llm_text(system, "\n".join(lines))

    def generate_report_brief(self, report_id: int) -> Optional[str]:
        """对单份日报生成 LLM 简报"""
        report = self.get_report(report_id)
        if not report:
            return None
        ctx = (
            f"员工{report.employee_id} 的日报（{report.report_date}）：\n"
            f"正文：{report.content or '无'}\n"
            f"关键进展：{'、'.join(report.key_progress or []) or '无'}\n"
            f"风险：{'、'.join(report.risks or []) or '无'}\n"
            f"下一步：{report.next_plan or '无'}"
        )
        system = "你是主管助理。对这份员工日报生成一段简短点评（亮点+需关注点），80字以内。"
        return _crm_llm_text(system, ctx)

    def get_report(self, report_id: int) -> Optional[EmployeeDailyReport]:
        return self.db.query(EmployeeDailyReport).filter(
            EmployeeDailyReport.id == report_id
        ).first()

    def list_reports(
        self,
        employee_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[EmployeeDailyReport]:
        """条件查询日报列表（所有参数可选，不传则不做对应过滤）"""
        query = self.db.query(EmployeeDailyReport)

        if employee_id:
            query = query.filter(EmployeeDailyReport.employee_id == employee_id)
        if start_date:
            query = query.filter(EmployeeDailyReport.report_date >= start_date)
        if end_date:
            query = query.filter(EmployeeDailyReport.report_date <= end_date)
        # 动态拼接过滤条件：只对实际传入的参数添加 WHERE 子句

        return query.order_by(EmployeeDailyReport.report_date.desc()).all()

    def get_summary(
        self, report_date: date,
    ) -> DailyReportManagementSummary:
        """
        日报汇总（管理层用）
        - 统计指定日期的日报提交情况
        - 汇总每个员工的关键进展和风险
        - 调用 LLM 生成整体工作总览 ai_overview（不可用时为空）
        """
        query = self.db.query(EmployeeDailyReport).filter(
            EmployeeDailyReport.report_date == report_date
        )

        reports = query.all()

        employees = [
            EmployeeSummaryItem(
                employee_id=r.employee_id,
                key_progress=r.key_progress or [],
                risks=r.risks or [],
            )
            for r in reports
        ]
        # 列表推导式：将每条日报记录转为汇总条目，提取管理层关心的关键字段

        ai_overview = self._llm_daily_overview(employees) or ""
        return DailyReportManagementSummary(
            report_date=report_date,
            total_submitted=len(reports),
            employees=employees,
            ai_overview=ai_overview,
        )

    def _llm_daily_overview(self, employees: List[EmployeeSummaryItem]) -> Optional[str]:
        """调用 LLM 基于团队日报生成整体工作总览"""
        if not employees:
            return None
        lines = [
            f"- 员工{e.employee_id}：进展[{'、'.join(e.key_progress or []) or '无'}]；"
            f"风险[{'、'.join(e.risks or []) or '无'}]"
            for e in employees
        ]
        system = "你是管理层助理。基于以下团队日报，生成一段整体工作总览（进展亮点+主要风险+建议关注），150字以内。"
        return _crm_llm_text(system, "\n".join(lines))


# ============================================================
