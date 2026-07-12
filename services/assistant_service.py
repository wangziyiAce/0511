"""
企业智能助手 — 核心服务层
===========================================
实现 NL2SQL + NL2API 的智能助手功能。

架构:
    用户消息 → 意图识别 → 路由分发 → SQL/API 执行 → 结果格式化 → 返回

三大模块:
    1. NL2SQL — 自然语言生成 SQL 查询（仅 SELECT，CRM 表白名单）
    2. NL2API — 自然语言选择 API 并提取参数调用
    3. 闲聊 — 直接 LLM 回复

安全机制（NL2SQL）:
    - 关键词黑名单（禁止 INSERT/UPDATE/DELETE 等）
    - 表白名单（仅允许 crm_lead / crm_follow_up / employee_daily_report）
    - 语法解析（只允许单条 SELECT）
    - 执行限制（自动 LIMIT 100，超时 5 秒）

API 注册表:
    - 数据驱动，字典列表定义所有可调用的 API
    - 新增 API 只需在注册表中添加一项，无需改核心逻辑
"""

import json
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import LLM_API_KEY, LLM_API_URL, LLM_MODEL, LLM_TIMEOUT
from models.crm import AssistantMessage, AssistantSession
from schemas.crm import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantMessageResponse,
    AssistantSessionResponse,
)
from services.crm_service import CrmService, EmployeeService

logger = logging.getLogger(__name__)


# ============================================================
# 第 1 段：LLM 调用封装
# ============================================================

def _call_llm(system_prompt: str, user_content: str) -> Optional[str]:
    """
    调用 LLM Chat Completions API（同步阻塞模式）。

    参数:
        system_prompt: 系统提示词（设定 AI 角色和输出格式）
        user_content:  用户消息（具体的业务数据）

    返回:
        LLM 返回的文本内容（message.content），失败时返回 None
    """
    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY 未配置，跳过 LLM 调用")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 包未安装，请执行: pip install openai>=1.30.0")
        return None

    try:
        client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_API_URL,
            timeout=LLM_TIMEOUT,
        )

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,  # 低温度，输出更确定（适合结构化任务）
        )

        content = response.choices[0].message.content
        logger.info(f"LLM 调用成功: model={LLM_MODEL}")
        return content

    except Exception as e:
        logger.error(f"LLM 调用失败: {type(e).__name__}: {e}")
        return None


def _extract_json(text: str) -> Optional[dict]:
    """
    从 LLM 返回的文本中提取 JSON 对象。

    LLM 常见的输出格式问题:
      1. markdown 代码块包裹: ```json {...} ```
      2. JSON 前后有多余文字
      3. 尾逗号（trailing comma）
    """
    if not text or not text.strip():
        return None

    # 去除 markdown 代码块标记
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.replace("```", "")

    # 尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 提取第一个 {...} 块
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 修复尾逗号
        fixed = re.sub(r",\s*}", "}", json_str)
        fixed = re.sub(r",\s*]", "]", fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法从 LLM 输出中提取 JSON")
    return None


def is_llm_available() -> bool:
    """检查 LLM 服务是否可用（只检查配置，不做网络请求）。"""
    if not LLM_API_KEY:
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


# ============================================================
# 第 2 段：API 注册表
# ============================================================
# 数据驱动设计：新增 API 只需在列表中添加一项，无需改代码。

API_REGISTRY: List[Dict[str, Any]] = [
    # ==================== 客户管理 ====================
    {
        "id": "list_leads",
        "name": "查询意向客户列表",
        "description": "查询客户列表，支持按状态、负责人、关键词筛选。可分页。",
        "method": "GET",
        "path": "/api/v1/crm/leads",
        "parameters": {
            "status": {"type": "string", "required": False, "description": "状态筛选: new/contacting/qualified/signed/lost"},
            "owner_employee_id": {"type": "int", "required": False, "description": "负责人 ID"},
            "keyword": {"type": "string", "required": False, "description": "关键词（姓名/联系方式）"},
            "page": {"type": "int", "required": False, "description": "页码，默认 1"},
            "page_size": {"type": "int", "required": False, "description": "每页条数，默认 20"},
        },
    },
    {
        "id": "get_lead",
        "name": "查询单个客户详情",
        "description": "根据客户 ID 查询客户详细信息。",
        "method": "GET",
        "path": "/api/v1/crm/leads/{id}",
        "parameters": {
            "id": {"type": "int", "required": True, "description": "客户 ID"},
        },
    },
    {
        "id": "create_lead",
        "name": "新增意向客户",
        "description": "录入一个新的意向客户。customer_name 和 owner_employee_id 必填。",
        "method": "POST",
        "path": "/api/v1/crm/leads",
        "parameters": {
            "customer_name": {"type": "string", "required": True, "description": "客户姓名"},
            "contact_info": {"type": "string", "required": False, "description": "联系方式"},
            "education_level": {"type": "string", "required": False, "description": "学历层次"},
            "intended_country": {"type": "string", "required": False, "description": "意向国家"},
            "intended_major": {"type": "string", "required": False, "description": "意向专业"},
            "source_channel": {"type": "string", "required": False, "description": "来源渠道"},
            "background_info": {"type": "string", "required": False, "description": "背景说明"},
            "remark": {"type": "string", "required": False, "description": "备注"},
            "owner_employee_id": {"type": "int", "required": True, "description": "负责员工 ID"},
        },
    },
    {
        "id": "update_lead",
        "name": "更新客户信息",
        "description": "更新客户的基本信息（部分更新）。",
        "method": "PUT",
        "path": "/api/v1/crm/leads/{id}",
        "parameters": {
            "id": {"type": "int", "required": True, "description": "客户 ID"},
            "customer_name": {"type": "string", "required": False, "description": "客户姓名"},
            "contact_info": {"type": "string", "required": False, "description": "联系方式"},
            "education_level": {"type": "string", "required": False, "description": "学历"},
            "intended_country": {"type": "string", "required": False, "description": "意向国家"},
            "intended_major": {"type": "string", "required": False, "description": "意向专业"},
            "remark": {"type": "string", "required": False, "description": "备注"},
        },
    },
    {
        "id": "update_lead_status",
        "name": "更新客户状态",
        "description": "更新客户的销售状态。状态流转有规则限制。",
        "method": "PUT",
        "path": "/api/v1/crm/leads/{id}/status",
        "parameters": {
            "id": {"type": "int", "required": True, "description": "客户 ID"},
            "status": {"type": "string", "required": True, "description": "目标状态: new/contacting/qualified/signed/lost"},
            "lost_reason": {"type": "string", "required": False, "description": "流失原因（状态为 lost 时必填）"},
        },
    },
    # ==================== 跟进记录 ====================
    {
        "id": "create_follow_up",
        "name": "新增跟进记录",
        "description": "为客户添加一条跟进记录。",
        "method": "POST",
        "path": "/api/v1/crm/leads/{lead_id}/follow-ups",
        "parameters": {
            "lead_id": {"type": "int", "required": True, "description": "客户 ID"},
            "employee_id": {"type": "int", "required": True, "description": "跟进员工 ID"},
            "follow_type": {"type": "string", "required": True, "description": "跟进方式: phone/wechat/meeting/email/other"},
            "content": {"type": "string", "required": True, "description": "跟进内容"},
            "next_plan": {"type": "string", "required": False, "description": "下次计划"},
        },
    },
    {
        "id": "list_follow_ups",
        "name": "查询跟进记录",
        "description": "查询某个客户的所有跟进记录。",
        "method": "GET",
        "path": "/api/v1/crm/leads/{lead_id}/follow-ups",
        "parameters": {
            "lead_id": {"type": "int", "required": True, "description": "客户 ID"},
        },
    },
    # ==================== 员工日报 ====================
    {
        "id": "create_daily_report",
        "name": "提交日报",
        "description": "提交员工日报。可只传 raw_content，系统自动填充 content。",
        "method": "POST",
        "path": "/api/v1/employee/daily-reports",
        "parameters": {
            "employee_id": {"type": "int", "required": True, "description": "员工 ID"},
            "report_date": {"type": "string", "required": True, "description": "日报日期，格式 YYYY-MM-DD"},
            "raw_content": {"type": "string", "required": False, "description": "口述原文"},
            "content": {"type": "string", "required": False, "description": "结构化内容"},
            "key_progress": {"type": "array", "required": False, "description": "关键进展列表"},
            "risks": {"type": "array", "required": False, "description": "风险项列表"},
            "next_plan": {"type": "string", "required": False, "description": "明日计划"},
        },
    },
    {
        "id": "list_daily_reports",
        "name": "查询日报列表",
        "description": "查询日报列表，支持按员工和日期筛选。",
        "method": "GET",
        "path": "/api/v1/employee/daily-reports",
        "parameters": {
            "employee_id": {"type": "int", "required": False, "description": "员工 ID"},
            "start_date": {"type": "string", "required": False, "description": "起始日期"},
            "end_date": {"type": "string", "required": False, "description": "截止日期"},
        },
    },
    {
        "id": "daily_report_summary",
        "name": "日报汇总",
        "description": "查看某天的日报汇总（管理层用）。",
        "method": "GET",
        "path": "/api/v1/employee/daily-reports/summary",
        "parameters": {
            "report_date": {"type": "string", "required": True, "description": "汇总日期，格式 YYYY-MM-DD"},
        },
    },
]

# 将注册表转为字典，方便按 ID 查找
API_REGISTRY_DICT = {api["id"]: api for api in API_REGISTRY}


# ============================================================
# 第 3 段：NL2SQL 引擎
# ============================================================

# 允许查询的表白名单
SQL_TABLE_WHITELIST = {
    "crm_lead",
    "crm_follow_up",
    "employee_daily_report",
}

# SQL 关键词黑名单
SQL_KEYWORD_BLACKLIST = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "REPLACE", "MERGE", "CALL",
    "EXEC", "EXECUTE", "INTO", "VALUES",
}

# 表结构描述（提供给 LLM）
CRM_TABLE_SCHEMA = """
表 1: crm_lead（意向客户表）
字段:
  - id: 主键
  - customer_name: 客户姓名
  - contact_info: 联系方式
  - gender: 性别（M/F/U）
  - age: 年龄
  - education_level: 学历层次
  - intended_country: 意向国家
  - intended_major: 意向专业
  - source_channel: 来源渠道
  - status: 销售状态（new/contacting/qualified/signed/lost）
  - lost_reason: 流失原因
  - owner_employee_id: 负责员工 ID
  - last_contact_time: 最后联系时间
  - create_time: 创建时间
  - update_time: 更新时间

表 2: crm_follow_up（跟进记录表）
字段:
  - id: 主键
  - lead_id: 客户 ID
  - employee_id: 跟进员工 ID
  - follow_type: 跟进方式（phone/wechat/meeting/email/other）
  - content: 跟进内容
  - next_plan: 下次计划
  - create_time: 创建时间

表 3: employee_daily_report（员工日报表）
字段:
  - id: 主键
  - employee_id: 员工 ID
  - report_date: 日报日期
  - status: 状态（draft/submitted）
  - raw_content: 原始口述内容
  - content: 结构化内容
  - key_progress: 关键进展（JSON 数组）
  - risks: 风险项（JSON 数组）
  - next_plan: 明日计划
  - create_time: 创建时间
"""


def _generate_sql(user_message: str) -> Optional[str]:
    """调用 LLM 生成 SQL 查询语句。"""

    system_prompt = f"""你是一个 SQL 生成助手。根据用户的自然语言问题，生成 MySQL 查询语句。

数据库表结构:
{CRM_TABLE_SCHEMA}

规则:
1. 只能生成 SELECT 查询，禁止 INSERT/UPDATE/DELETE 等操作
2. 只能查询以下表: crm_lead, crm_follow_up, employee_daily_report
3. 使用标准 MySQL 语法
4. 合理使用 WHERE、ORDER BY、LIMIT 等子句
5. LIKE 模糊查询使用 %关键词% 格式
6. 日期比较使用 DATE() 函数或直接比较
7. 不要使用子查询和 UNION

返回格式要求（必须是有效 JSON）:
{{"sql": "SELECT ... FROM ... WHERE ..."}}

示例:
用户问题: "有多少个联系中的客户"
返回: {{\"sql\": \"SELECT COUNT(*) AS count FROM crm_lead WHERE status = 'contacting'\"}}

用户问题: "最近一周新增的客户"
返回: {{\"sql\": \"SELECT * FROM crm_lead WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY) ORDER BY create_time DESC LIMIT 20\"}}"""

    raw_text = _call_llm(system_prompt, user_message)
    if not raw_text:
        return None

    result = _extract_json(raw_text)
    if not result or "sql" not in result:
        logger.warning("LLM 未返回有效的 SQL")
        return None

    return result["sql"]


def _validate_sql(sql: str) -> Tuple[bool, str]:
    """
    校验 SQL 语句安全性。

    返回: (是否通过, 错误消息)
    """
    sql_upper = sql.upper().strip()

    # 1. 检查关键词黑名单
    for keyword in SQL_KEYWORD_BLACKLIST:
        # 使用正则匹配独立单词，避免误判（如 SELECT 不应匹配到 "SELECTED"）
        if re.search(rf"\b{keyword}\b", sql_upper):
            return False, f"禁止使用的关键词: {keyword}"

    # 2. 检查表白名单
    # 提取 SQL 中出现的表名
    tables_found = re.findall(r"\bFROM\s+(\w+)", sql_upper)
    tables_found += re.findall(r"\bJOIN\s+(\w+)", sql_upper)

    for table in tables_found:
        if table.lower() not in SQL_TABLE_WHITELIST:
            return False, f"禁止查询的表: {table}"

    # 3. 只允许 SELECT
    if not sql_upper.startswith("SELECT"):
        return False, "只允许 SELECT 查询"

    # 4. 禁止 UNION
    if "UNION" in sql_upper:
        return False, "禁止使用 UNION"

    # 5. 禁止分号（防止多语句注入）
    if ";" in sql:
        return False, "禁止多语句执行"

    return True, ""


def _execute_sql(db: Session, sql: str) -> Tuple[List[Dict], str]:
    """
    执行 SQL 查询。

    返回: (结果列表, 错误消息)
    """
    try:
        # 自动追加 LIMIT 100
        sql_upper = sql.upper()
        if "LIMIT" not in sql_upper:
            sql = sql.rstrip(";") + " LIMIT 100"

        result = db.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()

        # 转为字典列表
        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                # 处理特殊类型
                if isinstance(val, Decimal):
                    val = float(val)
                elif isinstance(val, datetime):
                    val = val.isoformat()
                row_dict[col] = val
            data.append(row_dict)

        return data, ""

    except Exception as e:
        logger.error(f"SQL 执行失败: {e}")
        return [], str(e)


def _format_sql_result(user_message: str, sql: str, data: List[Dict]) -> str:
    """调用 LLM 将 SQL 查询结果格式化为自然语言回复。"""

    system_prompt = """你是一个数据分析师助手。根据用户的原始问题和 SQL 查询结果，生成清晰的自然语言回复。

规则:
1. 用简洁的中文回答用户问题
2. 如果结果为空，说明没有找到匹配的数据
3. 如果有多条记录，可以列举关键信息或总结
4. 数字要准确，不要编造数据"""

    user_content = f"""用户问题: {user_message}

执行的 SQL:
{sql}

查询结果（JSON）:
{json.dumps(data[:10], ensure_ascii=False, indent=2)}
{"（结果已截断，仅显示前 10 条）" if len(data) > 10 else ""}

请生成自然语言回复。"""

    return _call_llm(system_prompt, user_content) or "查询完成，但格式化失败。"


# ============================================================
# 第 4 段：NL2API 引擎
# ============================================================

def _select_api(user_message: str) -> Optional[Dict]:
    """
    调用 LLM 从注册表选择 API 并提取参数。

    返回: {"api_id": "...", "params": {...}}
    """
    # 构造 API 描述
    api_list_text = "\n".join([
        f"- {api['id']}: {api['name']} — {api['description']}"
        for api in API_REGISTRY
    ])

    system_prompt = f"""你是一个 API 路由助手。根据用户的自然语言请求，选择最合适的 API 并提取参数。

可用 API 列表:
{api_list_text}

规则:
1. 根据用户意图选择最匹配的 API
2. 从用户消息中提取参数值
3. 如果用户没有提供某个必填参数，参数值设为 null
4. 返回有效的 JSON 格式

返回格式:
{{"api_id": "API_ID", "params": {{参数名: 值, ...}}}}

示例:
用户: "帮我录入一个新客户叫张三，手机号 13800138000，负责人是 2 号"
返回: {{\"api_id\": \"create_lead\", \"params\": {{\"customer_name\": \"张三\", \"contact_info\": \"13800138000\", \"owner_employee_id\": 2}}}}"""

    raw_text = _call_llm(system_prompt, user_message)
    if not raw_text:
        return None

    result = _extract_json(raw_text)
    if not result or "api_id" not in result:
        logger.warning("LLM 未返回有效的 API 选择")
        return None

    return result


def _execute_api(db: Session, api_id: str, params: Dict) -> Tuple[Any, str]:
    """
    执行 API 调用（内部调用 Service 层）。

    返回: (执行结果, 错误消息)
    """
    if api_id not in API_REGISTRY_DICT:
        return None, f"未知的 API: {api_id}"

    api_config = API_REGISTRY_DICT[api_id]

    try:
        # ==================== 客户管理 ====================
        if api_id == "list_leads":
            service = CrmService(db)
            from schemas.crm import LeadListResponse
            from datetime import date as date_type
            result = service.list_leads(
                status=params.get("status"),
                owner_employee_id=params.get("owner_employee_id"),
                keyword=params.get("keyword"),
                page=params.get("page", 1),
                page_size=params.get("page_size", 20),
            )
            return result.model_dump(), ""

        elif api_id == "get_lead":
            service = CrmService(db)
            lead = service.get_lead(params["id"])
            if not lead:
                return None, "客户不存在"
            from schemas.crm import LeadResponse
            return LeadResponse.model_validate(lead).model_dump(), ""

        elif api_id == "create_lead":
            from schemas.crm import LeadCreate
            service = CrmService(db)
            data = LeadCreate(**params)
            lead = service.create_lead(data)
            from schemas.crm import LeadResponse
            return LeadResponse.model_validate(lead).model_dump(), ""

        elif api_id == "update_lead":
            from schemas.crm import LeadUpdate
            service = CrmService(db)
            lead_id = params.pop("id")
            data = LeadUpdate(**params)
            lead = service.update_lead(lead_id, data)
            if not lead:
                return None, "客户不存在"
            from schemas.crm import LeadResponse
            return LeadResponse.model_validate(lead).model_dump(), ""

        elif api_id == "update_lead_status":
            from schemas.crm import LeadStatusUpdate
            service = CrmService(db)
            lead_id = params.pop("id")
            data = LeadStatusUpdate(**params)
            lead = service.update_lead_status(lead_id, data)
            from schemas.crm import LeadResponse
            return LeadResponse.model_validate(lead).model_dump(), ""

        # ==================== 跟进记录 ====================
        elif api_id == "create_follow_up":
            from schemas.crm import FollowUpCreate
            service = CrmService(db)
            lead_id = params.pop("lead_id")
            data = FollowUpCreate(**params)
            follow_up = service.create_follow_up(lead_id, data)
            from schemas.crm import FollowUpResponse
            return FollowUpResponse.model_validate(follow_up).model_dump(), ""

        elif api_id == "list_follow_ups":
            service = CrmService(db)
            follow_ups = service.list_follow_ups(params["lead_id"])
            from schemas.crm import FollowUpResponse
            return [FollowUpResponse.model_validate(f).model_dump() for f in follow_ups], ""

        # ==================== 员工日报 ====================
        elif api_id == "create_daily_report":
            from schemas.crm import DailyReportCreate
            from datetime import datetime as dt
            service = EmployeeService(db)
            # 处理日期格式
            if "report_date" in params and isinstance(params["report_date"], str):
                params["report_date"] = dt.strptime(params["report_date"], "%Y-%m-%d").date()
            data = DailyReportCreate(**params)
            report = service.create_report(data)
            from schemas.crm import DailyReportResponse
            return DailyReportResponse.model_validate(report).model_dump(), ""

        elif api_id == "list_daily_reports":
            from datetime import datetime as dt
            service = EmployeeService(db)
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            if start_date:
                start_date = dt.strptime(start_date, "%Y-%m-%d").date()
            if end_date:
                end_date = dt.strptime(end_date, "%Y-%m-%d").date()
            reports = service.list_reports(
                employee_id=params.get("employee_id"),
                start_date=start_date,
                end_date=end_date,
            )
            from schemas.crm import DailyReportResponse
            return [DailyReportResponse.model_validate(r).model_dump() for r in reports], ""

        elif api_id == "daily_report_summary":
            from datetime import datetime as dt
            service = EmployeeService(db)
            report_date = dt.strptime(params["report_date"], "%Y-%m-%d").date()
            result = service.get_summary(report_date=report_date)
            return result.model_dump(), ""

        else:
            return None, f"API 未实现: {api_id}"

    except Exception as e:
        logger.error(f"API 执行失败: {api_id}, {e}")
        return None, str(e)


def _format_api_result(user_message: str, api_id: str, result: Any) -> str:
    """调用 LLM 将 API 执行结果格式化为自然语言回复。"""

    api_config = API_REGISTRY_DICT.get(api_id, {})

    system_prompt = """你是一个助手。根据用户的原始请求和 API 执行结果，生成清晰的自然语言回复。

规则:
1. 用简洁的中文回复
2. 确认操作是否成功
3. 如果有创建/更新的数据，说明关键信息
4. 如果有错误，解释原因"""

    user_content = f"""用户请求: {user_message}

调用的 API: {api_id} — {api_config.get('name', '')}

执行结果:
{json.dumps(result, ensure_ascii=False, indent=2) if result else '无'}

请生成自然语言回复。"""

    return _call_llm(system_prompt, user_content) or "操作完成。"


# ============================================================
# 第 5 段：意图识别与核心编排
# ============================================================

INTENT_SYSTEM_PROMPT = """你是一个意图识别助手。分析用户消息，判断用户想要做什么。

用户可能的意图类型:
1. sql — 查询数据（如"有多少客户"、"最近一周新增了几个"、"看看客户 3 号的信息"）
2. api — 执行操作（如"帮我录入新客户"、"更新客户状态"、"提交日报"）
3. text — 闲聊或其他（如"你好"、"谢谢"、"你是谁"）

规则:
1. 如果用户想查数据、看报表，返回 sql
2. 如果用户想新增、修改、删除数据，返回 api
3. 其他情况返回 text

返回格式（必须是有效 JSON）:
{"intent": "sql" 或 "api" 或 "text"}

示例:
用户: "现在有多少个联系中的客户"
返回: {"intent": "sql"}

用户: "帮我录入一个新客户叫王五"
返回: {"intent": "api"}

用户: "你好"
返回: {"intent": "text"}"""


class AssistantService:
    """智能助手服务"""

    def __init__(self, db: Session):
        self.db = db

    def chat(self, request: AssistantChatRequest, employee_id: int) -> AssistantChatResponse:
        """
        处理聊天请求。

        流程:
          1. 获取或创建会话
          2. 保存用户消息
          3. 意图识别
          4. 路由执行（SQL/API/Text）
          5. 保存助手回复
          6. 返回响应
        """
        # 1. 获取或创建会话
        session = self._get_or_create_session(request, employee_id)

        # 2. 保存用户消息
        user_message = AssistantMessage(
            session_id=session.session_id,
            role="user",
            content=request.message,
        )
        self.db.add(user_message)
        self.db.commit()

        # 3. 意图识别
        intent_result = self._recognize_intent(request.message)
        intent = intent_result.get("intent", "text")

        # 4. 路由执行
        reply_text = ""
        action_type = None
        action_data = None
        action_detail = None

        if intent == "sql":
            # NL2SQL 路径
            reply_text, action_data, action_detail = self._handle_sql_intent(request.message)
            action_type = "sql"

        elif intent == "api":
            # NL2API 路径
            reply_text, action_data, action_detail = self._handle_api_intent(request.message)
            action_type = "api"

        else:
            # 闲聊路径
            reply_text = self._handle_text_intent(request.message)
            action_type = "text"

        # 5. 保存助手回复
        assistant_message = AssistantMessage(
            session_id=session.session_id,
            role="assistant",
            content=reply_text,
            action_type=action_type,
            action_detail=action_detail,
            action_result=action_data,
        )
        self.db.add(assistant_message)

        # 更新会话最后消息时间
        session.last_message_time = datetime.utcnow()
        self.db.commit()
        self.db.refresh(assistant_message)

        # 6. 返回响应
        return AssistantChatResponse(
            session_id=session.session_id,
            reply_text=reply_text,
            action_type=action_type,
            action_data=action_data,
            create_time=assistant_message.create_time,
        )

    def _get_or_create_session(self, request: AssistantChatRequest, employee_id: int) -> AssistantSession:
        """获取或创建会话。"""
        if request.session_id:
            # 尝试获取已有会话
            session = self.db.query(AssistantSession).filter(
                AssistantSession.session_id == request.session_id,
                AssistantSession.employee_id == employee_id,
            ).first()
            if session:
                return session

        # 创建新会话
        session = AssistantSession(
            session_id=f"asst_{uuid.uuid4().hex[:16]}",
            employee_id=employee_id,
            status="active",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def _recognize_intent(self, message: str) -> Dict:
        """识别用户意图。"""
        raw_text = _call_llm(INTENT_SYSTEM_PROMPT, message)
        if not raw_text:
            return {"intent": "text"}

        result = _extract_json(raw_text)
        if not result:
            return {"intent": "text"}

        return result

    def _handle_sql_intent(self, message: str) -> Tuple[str, Optional[Dict], Optional[Dict]]:
        """处理 SQL 意图。返回: (回复文本, 结果数据, 详情)"""
        # 1. 生成 SQL
        sql = _generate_sql(message)
        if not sql:
            return "抱歉，我无法理解您的查询请求，请换种说法试试。", None, None

        # 2. 安全校验
        is_valid, error_msg = _validate_sql(sql)
        if not is_valid:
            logger.warning(f"SQL 校验失败: {error_msg}")
            return f"抱歉，查询请求包含不允许的操作：{error_msg}", None, {"sql": sql, "error": error_msg}

        # 3. 执行查询
        data, exec_error = _execute_sql(self.db, sql)
        if exec_error:
            return f"查询执行失败：{exec_error}", None, {"sql": sql, "error": exec_error}

        # 4. 格式化回复
        reply_text = _format_sql_result(message, sql, data)

        return reply_text, {"rows": data, "count": len(data)}, {"sql": sql}

    def _handle_api_intent(self, message: str) -> Tuple[str, Optional[Dict], Optional[Dict]]:
        """处理 API 意图。返回: (回复文本, 结果数据, 详情)"""
        # 1. 选择 API + 提取参数
        api_result = _select_api(message)
        if not api_result:
            return "抱歉，我无法理解您的请求，请换种说法试试。", None, None

        api_id = api_result.get("api_id")
        params = api_result.get("params", {})

        # 2. 执行 API
        result, error = _execute_api(self.db, api_id, params)
        if error:
            return f"操作失败：{error}", None, {"api_id": api_id, "params": params, "error": error}

        # 3. 格式化回复
        reply_text = _format_api_result(message, api_id, result)

        return reply_text, result, {"api_id": api_id, "params": params}

    def _handle_text_intent(self, message: str) -> str:
        """处理闲聊意图。"""
        system_prompt = """你是一个友好的企业智能助手。你是公司内部的 AI 助手，帮助员工查询数据、执行操作。

规则:
1. 用简洁友好的中文回复
2. 如果用户想查询数据或执行操作，引导他们描述具体需求
3. 不要编造数据或承诺你做不到的事情"""

        reply = _call_llm(system_prompt, message)
        return reply or "我在，请问有什么可以帮您？"

    def list_sessions(self, employee_id: int) -> List[AssistantSessionResponse]:
        """查询员工的会话列表。"""
        sessions = self.db.query(AssistantSession).filter(
            AssistantSession.employee_id == employee_id
        ).order_by(AssistantSession.last_message_time.desc()).limit(20).all()

        return [AssistantSessionResponse.model_validate(s) for s in sessions]

    def list_messages(self, session_id: str, employee_id: int) -> List[AssistantMessageResponse]:
        """查询会话消息历史。"""
        # 校验会话归属
        session = self.db.query(AssistantSession).filter(
            AssistantSession.session_id == session_id,
            AssistantSession.employee_id == employee_id,
        ).first()
        if not session:
            return []

        messages = self.db.query(AssistantMessage).filter(
            AssistantMessage.session_id == session_id
        ).order_by(AssistantMessage.create_time.asc()).all()

        return [AssistantMessageResponse.model_validate(m) for m in messages]
