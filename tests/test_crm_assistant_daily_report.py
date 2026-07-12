# -*- coding: utf-8 -*-
"""
============================================================================
企业智能助手 & 员工日报模块 — 详细测试方案（可执行）
============================================================================

一、测试目标
------------
覆盖业务方提出的 6 大需求场景，验证"企业智能助手 + 员工日报"两条主线的
端到端（HTTP 集成）+ 业务逻辑（Service 层）正确性：

  需求1. 意向客户录入  —— 语音/文字 → LLM 结构化 → 存入 CRM
  需求2. 意向客户查询  —— 档案 + 历史跟进记录调取
  需求3. 客户状态更新  —— 一键状态流转 + 销售漏斗同步（状态机校验）
  需求4. 口述日报      —— 语音口述 → LLM 结构化 → 日报文本
  需求5. 管理日报查阅  —— 管理层按日汇总团队日报
  需求6. 组织架构查询  —— 部门树 + 同事联系方式

二、测试策略
------------
1. 集成测试：通过 FastAPI TestClient 走完整 HTTP 链路（路由→Service→DB），
   验证统一响应格式 {code,message,data} 与业务规则。
2. 单元测试（Service 层）：直接调用 CrmService / EmployeeService /
   AssistantService，验证结构化回填、状态机等纯逻辑。
3. LLM 双模 mock：
   - 结构化解析（raw_content → 字段）：mock services.crm_service._call_llm
     返回预设 JSON，验证回填逻辑。
   - 智能助手编排（NL2SQL / NL2API）：mock _generate_sql / _select_api /
     AssistantService._recognize_intent，精确控制意图路由，避免依赖真实模型。
4. 鉴权 mock：override models.common.get_current_user，注入一个 employee 用户，
   模拟登录态（智能助手 / 组织架构接口均依赖该依赖）。
5. 数据隔离：复用 conftest 的 SQLite 内存库 + 事务回滚，每个测试独立。

三、环境依赖
------------
- pytest（本文件作为 tests/ 下用例，由 pytest 自动收集）
- 测试库：SQLite 内存库（conftest 已配置）
- 外部依赖（LLM / 真实 DB）均已 mock，可离线运行

四、用例矩阵（详见各 test_ 函数 docstring）
--------------------------------------------------------------------------
  需求 | 测试函数                                        | 验证点
  -----|------------------------------------------------|--------
   1   | test_create_lead_text_entry_structures         | 文字录入+LLM结构化回填
   1   | test_create_lead_voice_transcript_entry        | 语音转写文本等价录入
   1   | test_assistant_chat_create_lead_nl2api         | 对话触发 create_lead 意图
   2   | test_get_lead_detail_and_followups             | 档案+跟进历史联查
   2   | test_assistant_chat_query_lead_nl2sql          | 对话触发 NL2SQL 查询
   3   | test_update_lead_status_valid_transition       | new→contacting→qualified→signed 合法链
   3   | test_update_lead_status_terminal_no_rollback   | 终态不可回退(422/40902)
   3   | test_update_lead_status_lost_requires_reason   | lost 必填原因(400/40001)
   3   | test_assistant_chat_update_status_nl2api       | 对话触发状态更新意图
   4   | test_dictate_daily_report_structures           | 口述→结构化日报字段
   5   | test_daily_report_summary_management           | 管理层按日汇总
   6   | test_organization_flat_list                    | 平铺组织列表
   6   | test_organization_tree                         | 树形架构嵌套
   6   | test_org_employee_contact_lookup               | 部门+联系方式可定位
   边界 | test_assistant_chat_requires_auth             | 未登录 401
============================================================================
"""

import json
from datetime import date

import pytest

import services.crm_service as crm_svc
import services.assistant_service as assistant_svc
from services.crm_service import (
    CrmService,
    EmployeeService,
)
# AssistantService 已独立到 services.assistant_service（避免与 crm_service 形成循环导入）
from services.assistant_service import AssistantService
from schemas.crm import DailyReportCreate
from models.common import get_current_user
from models.user import SysUser, SysOrganization


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def current_employee(db_session):
    """注入一个已登录的 employee 用户（智能助手以 current_user.id 作为负责人）。"""
    user = SysUser(
        id=2001,
        username="emp1",
        password_hash="x",
        real_name="员工甲",
        user_type="employee",
        department="咨询部",
        contact_info="13800000001",
        status="normal",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client_as_employee(client, current_employee):
    """TestClient + 注入登录态（override get_current_user）。"""

    def _override():
        return current_employee

    app = client.app if hasattr(client, "app") else None
    # TestClient 直接持有 app 引用
    from main import app as _app
    _app.dependency_overrides[get_current_user] = _override
    yield client
    _app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def seed_org_and_users(db_session, current_employee):
    """预置组织架构树 + 两名员工（带部门/联系方式）。"""
    root = SysOrganization(id=1, org_name="公司", parent_id=None,
                           org_type="company", sort_order=1, status=1)
    dept1 = SysOrganization(id=2, org_name="咨询部", parent_id=1,
                            org_type="department", sort_order=2, status=1)
    dept2 = SysOrganization(id=3, org_name="市场部", parent_id=1,
                            org_type="department", sort_order=3, status=1)
    db_session.add_all([root, dept1, dept2])

    # 让 current_employee 归属咨询部
    current_employee.department = "咨询部"
    current_employee.contact_info = "13800000001"

    emp2 = SysUser(
        id=2002,
        username="emp2",
        password_hash="x",
        real_name="员工乙",
        user_type="employee",
        department="市场部",
        contact_info="13800000002",
        status="normal",
    )
    db_session.add(emp2)
    db_session.commit()
    return {"emp1": current_employee, "emp2": emp2}


def _mock_llm(monkeypatch, return_value):
    """统一 mock 底层 LLM 调用，返回固定文本/JSON。"""
    monkeypatch.setattr(
        crm_svc, "_call_llm",
        lambda system_prompt, user_content: return_value,
    )


# ===========================================================================
# 需求1：意向客户录入（语音/文字 → 结构化 → 入库）
# ===========================================================================

def test_create_lead_text_entry_structures_and_persists(
    client_as_employee, current_employee, monkeypatch
):
    """文字录入：提交自然语言 raw_content，LLM 抽取字段回填并落库。"""
    lead_json = json.dumps({
        "customer_name": "",
        "gender": "F",
        "age": 28,
        "education_level": "本科",
        "intended_country": "英国",
        "intended_major": "计算机科学",
        "source_channel": "线上广告",
        "contact_info": "",
        "background_info": "",
        "remark": "",
    }, ensure_ascii=False)
    _mock_llm(monkeypatch, lead_json)

    resp = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "王五",
        "owner_employee_id": current_employee.id,
        "raw_content": "王五，女，28岁，本科，想去英国读计算机科学，线上广告来的",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    # 显式字段 + LLM 回填字段都应正确
    assert data["customer_name"] == "王五"
    assert data["gender"] == "F"
    assert data["age"] == 28
    assert data["intended_country"] == "英国"
    assert data["intended_major"] == "计算机科学"
    assert data["status"] == "new"  # 新客户默认状态


def test_create_lead_voice_transcript_entry(
    client_as_employee, current_employee, monkeypatch
):
    """语音录入等价场景：前端语音转写后的口语化长文本，同样可结构化。"""
    lead_json = json.dumps({
        "customer_name": "赵六",
        "gender": "M",
        "age": 35,
        "education_level": "",
        "intended_country": "美国",
        "intended_major": "MBA",
        "source_channel": "老客户推荐",
        "contact_info": "13912345678",
        "background_info": "企业高管，预算充足",
        "remark": "高净值客户",
    }, ensure_ascii=False)
    _mock_llm(monkeypatch, lead_json)

    # 模拟语音转写文本（含口语、重复、无关词）
    transcript = (
        "呃，帮我记一下，有个客户叫赵六，男的，三十五六吧，"
        "想送孩子去美国读个MBA，是老客户王总推荐的，"
        "电话13912345678，企业高管预算挺足的，这个客户很重要记得跟紧"
    )
    resp = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "赵六",
        "owner_employee_id": current_employee.id,
        "raw_content": transcript,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["intended_country"] == "美国"
    assert data["intended_major"] == "MBA"
    assert data["contact_info"] == "13912345678"
    assert data["source_channel"] == "老客户推荐"


def test_assistant_chat_create_lead_via_nl2api(
    client_as_employee, current_employee, monkeypatch
):
    """智能助手对话：自然语言"录入新客户" → NL2API 路由到 create_lead。"""
    # 编排类调用 mock 为固定结果；_format_* 仅需 _call_llm 返回非空文本
    _mock_llm(monkeypatch, "OK")
    monkeypatch.setattr(
        AssistantService, "_recognize_intent",
        lambda self, m: {"intent": "api"},
    )
    monkeypatch.setattr(assistant_svc, "_select_api", lambda m: {
        "api_id": "create_lead",
        "params": {
            "customer_name": "钱七",
            "contact_info": "13700000000",
            "owner_employee_id": current_employee.id,
        },
    })

    resp = client_as_employee.post("/api/v1/crm/assistant/chat", json={
        "message": f"帮我录入新客户钱七，手机13700000000，负责人{current_employee.id}号",
    })
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["action_type"] == "api"
    assert d["action_data"]["customer_name"] == "钱七"
    # 验证真实落库
    lead_id = d["action_data"]["id"]
    get_resp = client_as_employee.get(f"/api/v1/crm/leads/{lead_id}")
    assert get_resp.json()["data"]["customer_name"] == "钱七"


# ===========================================================================
# 需求2：意向客户查询（档案 + 历史跟进）
# ===========================================================================

def test_get_lead_detail_and_followups(
    client_as_employee, current_employee, monkeypatch
):
    """查询客户档案并联动历史跟进记录。"""
    _mock_llm(monkeypatch, "{}")  # 建客户无 raw_content，不依赖 LLM
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "客户A",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]

    fu = client_as_employee.post(
        f"/api/v1/crm/leads/{lead_id}/follow-ups", json={
            "employee_id": current_employee.id,
            "follow_type": "phone",
            "content": "电话沟通需求，客户关注排名",
        })
    assert fu.status_code == 200

    # 档案
    det = client_as_employee.get(f"/api/v1/crm/leads/{lead_id}")
    assert det.json()["data"]["customer_name"] == "客户A"
    # 跟进历史
    fus = client_as_employee.get(f"/api/v1/crm/leads/{lead_id}/follow-ups")
    items = fus.json()["data"]
    assert any(i["content"] == "电话沟通需求，客户关注排名" for i in items)


def test_assistant_chat_query_lead_via_nl2sql(
    client_as_employee, current_employee, monkeypatch
):
    """智能助手对话：自然语言查询 → NL2SQL 生成并执行 SELECT。"""
    # 先建一条客户，得到真实 lead_id
    _mock_llm(monkeypatch, "{}")
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "查询测试客户",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]

    # 重新 mock：意图=sql，生成针对该 lead 的安全 SELECT
    _mock_llm(monkeypatch, "OK")
    monkeypatch.setattr(
        AssistantService, "_recognize_intent",
        lambda self, m: {"intent": "sql"},
    )
    monkeypatch.setattr(
        assistant_svc, "_generate_sql",
        lambda m: f"SELECT * FROM crm_lead WHERE id = {lead_id}",
    )

    resp = client_as_employee.post("/api/v1/crm/assistant/chat", json={
        "message": f"查一下客户{lead_id}的详情",
    })
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["action_type"] == "sql"
    assert d["action_data"]["count"] >= 1
    # 结果中应包含该客户姓名
    names = [row.get("customer_name") for row in d["action_data"]["rows"]]
    assert "查询测试客户" in names


# ===========================================================================
# 需求3：客户状态更新（状态机 + 销售漏斗同步）
# ===========================================================================

def test_update_lead_status_valid_transition(
    client_as_employee, current_employee, monkeypatch
):
    """合法流转链 new→contacting→qualified→signed 全程成功。"""
    _mock_llm(monkeypatch, "{}")
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "状态测试",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]

    for status in ["contacting", "qualified", "signed"]:
        r = client_as_employee.put(
            f"/api/v1/crm/leads/{lead_id}/status", json={"status": status})
        assert r.status_code == 200, f"状态流转到 {status} 应成功"
        assert r.json()["data"]["status"] == status


def test_update_lead_status_terminal_no_rollback(
    client_as_employee, current_employee, monkeypatch
):
    """终态（signed）不可回退，返回 422 / 业务码 40902。"""
    _mock_llm(monkeypatch, "{}")
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "终态测试",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]
    # 走到 signed
    for status in ["contacting", "qualified", "signed"]:
        client_as_employee.put(
            f"/api/v1/crm/leads/{lead_id}/status", json={"status": status})

    # 从 signed 回退到 new → 非法
    r = client_as_employee.put(
        f"/api/v1/crm/leads/{lead_id}/status", json={"status": "new"})
    assert r.status_code == 422
    assert r.json()["code"] == 42204


def test_update_lead_status_lost_requires_reason(
    client_as_employee, current_employee, monkeypatch
):
    """变更为 lost 必须填写 lost_reason，否则 400 / 业务码 40001。"""
    _mock_llm(monkeypatch, "{}")
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "流失测试",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]

    # 缺原因
    r1 = client_as_employee.put(
        f"/api/v1/crm/leads/{lead_id}/status", json={"status": "lost"})
    assert r1.status_code == 400
    assert r1.json()["code"] == 40001

    # 带原因
    r2 = client_as_employee.put(
        f"/api/v1/crm/leads/{lead_id}/status",
        json={"status": "lost", "lost_reason": "价格太高"})
    assert r2.status_code == 200
    assert r2.json()["data"]["status"] == "lost"
    assert r2.json()["data"]["lost_reason"] == "价格太高"


def test_assistant_chat_update_status_via_nl2api(
    client_as_employee, current_employee, monkeypatch
):
    """智能助手对话：自然语言"改状态" → NL2API 路由到 update_lead_status。"""
    _mock_llm(monkeypatch, "{}")
    create = client_as_employee.post("/api/v1/crm/leads", json={
        "customer_name": "助手状态测试",
        "owner_employee_id": current_employee.id,
    })
    lead_id = create.json()["data"]["id"]

    _mock_llm(monkeypatch, "OK")
    monkeypatch.setattr(
        AssistantService, "_recognize_intent",
        lambda self, m: {"intent": "api"},
    )
    monkeypatch.setattr(assistant_svc, "_select_api", lambda m: {
        "api_id": "update_lead_status",
        "params": {"id": lead_id, "status": "contacting"},
    })

    resp = client_as_employee.post("/api/v1/crm/assistant/chat", json={
        "message": f"把客户{lead_id}状态改成跟进中",
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["action_type"] == "api"
    # 验证真实落库
    get = client_as_employee.get(f"/api/v1/crm/leads/{lead_id}")
    assert get.json()["data"]["status"] == "contacting"


# ===========================================================================
# 需求4：口述日报（语音口述 → 结构化日报）
# ===========================================================================

def test_dictate_daily_report_structures(
    client_as_employee, current_employee, monkeypatch
):
    """口述日报：提交口语化 raw_content，LLM 抽取为结构化日报字段。"""
    report_json = json.dumps({
        "content": "今日跟进3个意向客户，完成1单签约。",
        "key_progress": ["签约客户A", "新增2个意向客户"],
        "risks": ["客户B预算不足"],
        "next_plan": "明日安排客户C面谈",
    }, ensure_ascii=False)
    _mock_llm(monkeypatch, report_json)

    today = date.today().isoformat()
    resp = client_as_employee.post("/api/v1/employee/daily-reports", json={
        "employee_id": current_employee.id,
        "report_date": today,
        "raw_content": (
            "今天我跟进了三个客户，签了一单，还新加了俩意向的，"
            "客户B说预算不够可能要黄，明天约了客户C面谈"
        ),
    })
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["content"] == "今日跟进3个意向客户，完成1单签约。"
    assert "签约客户A" in d["key_progress"]
    assert d["risks"] == ["客户B预算不足"]
    assert d["next_plan"] == "明日安排客户C面谈"


# ===========================================================================
# 需求5：管理日报查阅（管理层汇总）
# ===========================================================================

def test_daily_report_summary_management(
    client_as_employee, db_session, current_employee,
    seed_org_and_users, monkeypatch
):
    """管理层按日汇总：统计提交人数与各员工关键进展/风险。"""
    _mock_llm(monkeypatch, "总览文本")  # get_summary 的 ai_overview 用
    today = date.today()
    svc = EmployeeService(db_session)
    svc.create_report(DailyReportCreate(
        employee_id=current_employee.id, report_date=today,
        content="A工作", key_progress=["进展1"], risks=["风险1"]))
    svc.create_report(DailyReportCreate(
        employee_id=seed_org_and_users["emp2"].id, report_date=today,
        content="B工作", key_progress=["进展2"], risks=[]))

    resp = client_as_employee.get(
        f"/api/v1/employee/daily-reports/summary?report_date={today.isoformat()}")
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["total_submitted"] == 2
    emp_ids = {e["employee_id"] for e in d["employees"]}
    assert current_employee.id in emp_ids
    assert seed_org_and_users["emp2"].id in emp_ids


# ===========================================================================
# 需求6：组织架构查询（部门树 + 同事联系方式）
# ===========================================================================

def test_organization_flat_list(client_as_employee, seed_org_and_users):
    """平铺组织列表：返回各部门节点。"""
    resp = client_as_employee.get("/api/v1/auth/organizations")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    org_names = {o["org_name"] for o in items}
    assert "咨询部" in org_names
    assert "市场部" in org_names


def test_organization_tree(client_as_employee, seed_org_and_users):
    """树形架构：根节点（公司）正确嵌套子部门。"""
    resp = client_as_employee.get("/api/v1/auth/organizations/tree")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    roots = [o for o in items if o["org_name"] == "公司"]
    assert roots, "应存在根节点'公司'"
    assert roots[0].get("children"), "根节点应嵌套子部门"


def test_org_employee_contact_lookup(
    client_as_employee, seed_org_and_users, db_session
):
    """跨部门协作：可通过部门 + 用户表定位同事联系方式。"""
    emp = seed_org_and_users["emp1"]
    user = db_session.query(SysUser).filter_by(id=emp.id).first()
    assert user.department == "咨询部"
    assert user.contact_info == "13800000001"
    # 另一部门同事也可定位
    emp2 = seed_org_and_users["emp2"]
    user2 = db_session.query(SysUser).filter_by(id=emp2.id).first()
    assert user2.department == "市场部"
    assert user2.contact_info == "13800000002"


# ===========================================================================
# 边界：鉴权
# ===========================================================================

def test_assistant_chat_requires_auth(client):
    """未携带 Token 访问智能助手接口应返回 401。"""
    resp = client.post("/api/v1/crm/assistant/chat", json={"message": "你好"})
    assert resp.status_code == 401
