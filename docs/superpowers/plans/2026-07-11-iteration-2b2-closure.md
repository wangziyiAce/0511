# Iteration 2B.2 Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成智能报告助手 Iteration 2 的数据库迁移、同报告多轮闭环、测试隔离、证据编号、前端重试幂等和真实环境验收收口。

**Architecture:** 保留现有 Registry → Aggregator → Rules → Orchestrator 事实链路，在助手和前端现有边界内做最小修复。数据库采用版本化 MySQL SQL，不引入 Alembic；测试先固定每个缺口，再实施最小代码或 SQL，最终通过真实 MySQL、真实 LLM（配置可用时）和完整前后端回归验证。

**Tech Stack:** Python 3.13 当前虚拟环境（项目目标 Python 3.12）、FastAPI、Pydantic v2、SQLAlchemy、MySQL 8、pytest、React、TypeScript、Vitest、Vite。

## Global Constraints

- 不进入 Iteration 3，不增加周期对比、跨报告分析、Redis、RAG、LangGraph、多 Agent 或会话持久化。
- 不修改风险规则、Aggregator 指标口径、公共认证行为、其他业务模块和 `main.py`。
- 保留当前工作树中已有的 Iteration 2B/2B.1 未提交改动，只暂存和提交本轮明确触及的文件。
- 所有新增或重点修改的 Python 文件、类、函数和关键逻辑使用符合根 `AGENTS.md` 的中文 docstring/注释。
- 生产代码修改必须先有能够因缺口而失败的测试，并实际观察 RED → GREEN。
- `.env`、数据库密码和 LLM 密钥不得写入 Git、测试输出或完成报告。

---

### Task 1: 隔离助手配置并消除测试顺序污染

**Files:**
- Modify: `tests/test_report_assistant_v2_llm_contract.py`
- Modify: `tests/test_report_assistant_v2_async_contract.py`
- Modify: `tests/test_report_assistant_v2_http_and_idempotency.py`
- Modify only if root cause requires: `services/reporting/assistant/config.py`

**Interfaces:**
- Consumes: `services.reporting.assistant.config.settings`、`ReportIntentParser` 和现有 pytest `monkeypatch`。
- Produces: 每个测试结束后恢复助手环境和缓存的 autouse fixture；完整测试套件不再触发真实 LLM 网络调用。

- [ ] **Step 1: 固定当前失败顺序并保存根因证据**

运行完整范围，并确认异步契约测试日志出现真实模型调用或 `previous_week` 污染：

```powershell
$assistantTests = Get-ChildItem tests -Filter 'test_report_assistant_*.py' | Sort-Object Name | ForEach-Object FullName
.\.venv\Scripts\python.exe -m pytest @assistantTests tests/test_reporting_v2_contracts.py tests/test_reporting_v2_rules.py tests/test_reporting_v2_ai_generator.py -v
```

Expected: 现有基线 4 failed，失败集中在 idempotency/background task 测试。

- [ ] **Step 2: 写隔离回归测试或 fixture**

在最先污染全局配置的测试模块中增加测试，证明一次启用 LLM 的测试结束后，新建 `ReportAssistantService` 不会继承该状态：

```python
def test_llm_configuration_does_not_leak_to_next_test(monkeypatch):
    monkeypatch.setenv("REPORT_ASSISTANT_LLM_ENABLED", "false")
    reset_assistant_settings_for_test()
    service = ReportAssistantService()
    assert service._intent_parser._settings.llm_enabled is False
```

若当前没有 `reset_assistant_settings_for_test()`，先让测试以 `ImportError` 或状态仍为 `True` 的方式失败。

- [ ] **Step 3: 运行最小 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_v2_llm_contract.py::test_llm_configuration_does_not_leak_to_next_test -v
```

Expected: FAIL，证明缓存或模块级 settings 未恢复。

- [ ] **Step 4: 实现最小隔离机制**

优先在测试 fixture 中保存并恢复环境变量，并调用现有缓存清理入口。若生产配置使用 `lru_cache` 且没有安全入口，则在 `config.py` 增加仅负责重新读取环境的函数：

```python
def reload_assistant_settings() -> AssistantSettings:
    """重新读取助手环境配置，供测试隔离和受控配置刷新使用。"""
    global settings
    settings = AssistantSettings.from_env()
    return settings
```

测试模块 autouse fixture：

```python
@pytest.fixture(autouse=True)
def isolate_assistant_settings(monkeypatch):
    monkeypatch.setenv("REPORT_ASSISTANT_LLM_ENABLED", "false")
    monkeypatch.setenv("REPORT_ASSISTANT_ENABLED", "true")
    reload_assistant_settings()
    yield
    reload_assistant_settings()
```

实现前必须核对真实配置构造接口；保持相同职责，不复制配置解析。

- [ ] **Step 5: 验证 GREEN 和顺序稳定性**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_v2_llm_contract.py tests/test_report_assistant_v2_async_contract.py tests/test_report_assistant_v2_http_and_idempotency.py -v
```

Expected: 相关测试 0 failed，且日志无真实 LLM 网络调用。

- [ ] **Step 6: 提交隔离修复**

```powershell
git add tests/test_report_assistant_v2_llm_contract.py tests/test_report_assistant_v2_async_contract.py tests/test_report_assistant_v2_http_and_idempotency.py services/reporting/assistant/config.py
git commit -m "test: isolate report assistant settings"
```

只添加实际修改的文件。

---

### Task 2: 建立版本化 MySQL 迁移和 Schema 契约测试

**Files:**
- Create: `migrations/20260711_01_sync_report_generation_contract.up.sql`
- Create: `migrations/20260711_01_sync_report_generation_contract.down.sql`
- Create: `tests/test_report_assistant_database_contract.py`
- Create: `docs/智能报告助手_数据库枚举技术债.md`

**Interfaces:**
- Consumes: `REPORT_REGISTRY`、`REPORT_STATUS_VALUES`、`TRIGGER_SOURCE_VALUES`。
- Produces: MySQL 8 可执行的 upgrade/downgrade SQL 和静态契约测试。

- [ ] **Step 1: 写迁移契约 RED 测试**

```python
from pathlib import Path

from models.report import REPORT_STATUS_VALUES, TRIGGER_SOURCE_VALUES
from services.reporting.registry import REPORT_REGISTRY

UPGRADE = Path("migrations/20260711_01_sync_report_generation_contract.up.sql")


def test_upgrade_migration_covers_report_registry():
    sql = UPGRADE.read_text(encoding="utf-8")
    assert set(REPORT_REGISTRY).issubset(set(extract_contract_values(sql, "report_type")))


def test_upgrade_migration_covers_status_and_trigger_source():
    sql = UPGRADE.read_text(encoding="utf-8")
    assert set(REPORT_STATUS_VALUES) == set(extract_contract_values(sql, "status"))
    assert set(TRIGGER_SOURCE_VALUES) == set(extract_contract_values(sql, "trigger_source"))
```

`extract_contract_values()` 在测试文件内读取 SQL 中的机器可读注释，例如 `-- contract:status=pending,generating,completed,failed`。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_database_contract.py -v
```

Expected: FAIL，因为迁移文件不存在。

- [ ] **Step 3: 编写 upgrade SQL**

upgrade 采用当前 ORM 的真实目标契约：`report_type VARCHAR(64)`、四状态 ENUM、四来源 ENUM。SQL 使用存储过程式检查，在 ALTER 前对非法值执行 `SIGNAL SQLSTATE '45000'`：

```sql
-- contract:report_type=customer_ops,daily_summary,weekly_summary,psych_weekly,complaint_weekly,application_risk,sales_funnel,channel_roi,service_sla,action_closure
-- contract:status=pending,generating,completed,failed
-- contract:trigger_source=manual,schedule,retry,system

ALTER TABLE report_generation
  MODIFY COLUMN report_type VARCHAR(64) NOT NULL,
  MODIFY COLUMN status ENUM('pending','generating','completed','failed') NOT NULL DEFAULT 'pending',
  MODIFY COLUMN trigger_source ENUM('manual','schedule','retry','system') NOT NULL DEFAULT 'manual';
```

检查必须分别查询未知 status、未知 trigger_source 以及长度超过 64 的 report_type。Registry 子集测试只验证当前已知类型，数据库 VARCHAR 保留后续扩展能力。

- [ ] **Step 4: 编写 downgrade SQL**

downgrade 回到宽松、数据安全的迁移前兼容列类型，不删除当前合法数据：

```sql
ALTER TABLE report_generation
  MODIFY COLUMN report_type VARCHAR(64) NOT NULL,
  MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'pending',
  MODIFY COLUMN trigger_source VARCHAR(16) NOT NULL DEFAULT 'manual';
```

这一步撤销 ENUM 约束而不恢复无法从仓库证明的历史 ENUM 列表；文档明确该边界。

- [ ] **Step 5: 写技术债文档**

文档记录：Registry 是代码侧动态目录；数据库 report_type 使用 VARCHAR 避免每加类型都改 ENUM；status 和 trigger_source 仍是有限状态机，需要迁移；未来评审数据库 CHECK/VARCHAR 与 ENUM 的取舍。

- [ ] **Step 6: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_database_contract.py -v
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交迁移**

```powershell
git add migrations tests/test_report_assistant_database_contract.py docs/智能报告助手_数据库枚举技术债.md
git commit -m "feat: version report generation schema migration"
```

---

### Task 3: 为 MetricTrace 生成稳定 Evidence ID

**Files:**
- Modify: `tests/test_report_assistant_answer_grounding.py`
- Modify: `services/reporting/assistant/guardrails.py`

**Interfaces:**
- Consumes: `build_structured_evidence()`、`replace_evidence_placeholders()`。
- Produces: MetricTrace 对应的非空唯一 `E1...En` 证据。

- [ ] **Step 1: 增加四个失败测试**

```python
def test_metric_trace_evidence_has_non_empty_id():
    evidence = build_structured_evidence([metric_trace_tool_result()], report_id=12)
    assert evidence[0].evidence_id == "E1"


def test_metric_trace_evidence_id_is_unique():
    evidence = build_structured_evidence([two_metric_traces()], report_id=12)
    assert [item.evidence_id for item in evidence] == ["E1", "E2"]


def test_metric_trace_placeholder_is_replaced():
    mapping = build_evidence_map_structured([metric_trace_tool_result()], report_id=12)
    answer, warnings = replace_evidence_placeholders(answer="公式：{{E1}}", evidence_map=mapping)
    assert "{{E1}}" not in answer
    assert warnings == []


def test_metric_trace_unknown_evidence_is_rejected():
    mapping = build_evidence_map_structured([metric_trace_tool_result()], report_id=12)
    answer, warnings = replace_evidence_placeholders(answer="公式：{{E9}}", evidence_map=mapping)
    assert warnings
    assert "{{E9}}" not in answer
```

fixture 的 `metric_name` 使用真实的 `application_risk_score`，并包含 `source_tables`、`formula` 和 `filters`。

- [ ] **Step 2: 验证 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_answer_grounding.py -k "metric_trace" -v
```

Expected: 至少 `evidence_has_non_empty_id` 因当前 metric_name 白名单过滤或字段缺失而失败。

- [ ] **Step 3: 最小修改 MetricTrace 分支**

移除“只有 `_BUSINESS_METRIC_FIELDS` 才创建 trace evidence”的限制，对每条结构合法的 trace 调用 `_next_id()`，并映射：

```python
evidence_items.append(EvidenceItem(
    evidence_id=_next_id(),
    metric_name=metric_name,
    label=f"指标 {_metric_label(metric_name)} 追溯",
    value=trace.get("formula") or trace.get("reference") or metric_name,
    source_report_id=src_report_id,
    source_tables=trace.get("source_tables", []),
    formula=trace.get("formula"),
    source=tool_name,
    reference=trace.get("reference") or f"metric_traces.{metric_name}",
))
```

保持输入顺序，filters 通过 `reference` 或现有 Schema 可表达字段保留；不得扩展响应 Schema，除非测试证明字段已丢失。

- [ ] **Step 4: 验证 GREEN 和相关回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_answer_grounding.py tests/test_report_assistant_tools_v2.py -v
```

Expected: 0 failed。

- [ ] **Step 5: 提交 Evidence 修复**

```powershell
git add services/reporting/assistant/guardrails.py tests/test_report_assistant_answer_grounding.py
git commit -m "fix: assign metric trace evidence ids"
```

---

### Task 4: 前端错误重试复用原请求快照

**Files:**
- Modify: `frontend/src/types/report-assistant.ts`
- Modify: `frontend/src/components/report-assistant/ReportAssistantPanel.tsx`
- Modify: `frontend/src/__tests__/report-assistant-panel.test.tsx`

**Interfaces:**
- Consumes: `ReportAssistantMessageRequest`、`sendReportAssistantMessage()`。
- Produces: 用户消息上的 `clientRequestId` 和 `originalRequest`，以及可复用快照的发送函数。

- [ ] **Step 1: 写五个前端 RED 测试**

新增或调整测试，明确断言：新消息两次 ID 不同、追问 ID 是新值、重试 ID 与失败请求相同、重试 context 深度等于原快照、连续点击重试只调用一次 API。

核心断言：

```typescript
expect(secondRequest.client_request_id).toBe(firstRequest.client_request_id)
expect(secondRequest.conversation_context).toEqual(firstRequest.conversation_context)
expect(sendReportAssistantMessage).toHaveBeenCalledTimes(2)
```

- [ ] **Step 2: 运行 RED**

```powershell
Set-Location frontend
npm test -- report-assistant-panel.test.tsx
```

Expected: retry 测试因当前 `handleSend()` 总是创建新 ID、使用最新 context 而失败。

- [ ] **Step 3: 扩展消息类型**

```typescript
export interface AssistantMessage {
  // 既有字段保持不变
  clientRequestId?: string
  originalRequest?: ReportAssistantMessageRequest
}
```

- [ ] **Step 4: 将发送逻辑改为显式请求快照**

`handleSend` 接受可选的原始请求：

```typescript
const handleSend = useCallback(async (
  text: string,
  originalRequest?: ReportAssistantMessageRequest,
) => {
  const request = originalRequest ?? {
    message: text.trim(),
    conversation_context: structuredClone(context),
    client_request_id: generateClientRequestId(),
  }
  // 用户消息保存 request.client_request_id 和 request 本身。
  // API 调用直接发送 request，不再重新拼装 context 或 ID。
}, [context, isSending, isDisabled, addMessage, updateLastAssistantMessage])
```

重试从最后一个带 `originalRequest` 的用户消息读取快照，并传入 `handleSend`。必须在调用前检查 `isSending`，避免多次点击。

- [ ] **Step 5: 验证 GREEN**

```powershell
Set-Location frontend
npm test -- report-assistant-panel.test.tsx
```

Expected: panel 测试全部 PASS。

- [ ] **Step 6: 提交前端修复**

```powershell
git add frontend/src/types/report-assistant.ts frontend/src/components/report-assistant/ReportAssistantPanel.tsx frontend/src/__tests__/report-assistant-panel.test.tsx
git commit -m "fix: reuse assistant request id on retry"
```

---

### Task 5: 固定同 report_id 五步闭环与 403/404 契约

**Files:**
- Modify: `tests/test_report_assistant_multiturn_e2e.py`
- Modify: `tests/test_report_assistant_api.py`
- Modify only if tests expose defects: `services/reporting/assistant/service.py`
- Modify only if tests expose defects: `routers/report_assistant.py`

**Interfaces:**
- Consumes: `ReportAssistantService.handle_message()`、assistant `/messages` 路由。
- Produces: 五步唯一 report_id、assistant 状态查询、position 1 实体映射、403 和 404 的自动化保障。

- [ ] **Step 1: 写五步闭环 RED 测试**

使用同一 FakeDB/测试数据库构造一份完成报告，报告含 A1024、A1058、A1091，至少前两项进入 `risk_items`。按五个请求依次调用服务，并断言：

```python
assert len({turn.report_id for turn in turns}) == 1
assert turn2.intent == ReportAssistantIntent.QUERY_REPORT_STATUS
assert len(turn3.conversation_context.referenced_entities) >= 2
assert turn4.conversation_context.referenced_entities[0].entity_id == turn3.conversation_context.referenced_entities[0].entity_id
assert turn5.evidence[0].source_report_id == report_id
assert fake_db.report_generation_count == count_after_turn1
```

- [ ] **Step 2: 写真实路由状态 RED 测试**

通过 TestClient 或路由函数验证不存在报告状态查询：

```python
assert response.status_code == 404
assert response.json()["status"] == "not_found"
assert response.json()["intent"] == "query_report_status"
```

另写限制 report_type、他人报告、心理报告三种 403，并断言 `evidence == []` 且响应不包含敏感内容。

- [ ] **Step 3: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_multiturn_e2e.py tests/test_report_assistant_api.py -v
```

Expected: 缺失的五步或 HTTP 契约测试失败。

- [ ] **Step 4: 最小修复服务或路由**

只修复测试证明的问题：

- `query_report_status` 必须从 context 读取 report_id 并调用工具。
- 工具 not found 映射 `status=not_found`、HTTP 404。
- permission denied 映射 HTTP 403，响应不附加 evidence/report_type。
- drill_down 返回的 context 必须保存后端读取报告所得 entities；explain_risk 不信任客户端 metadata。

- [ ] **Step 5: 验证 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_multiturn_e2e.py tests/test_report_assistant_api.py tests/test_report_assistant_tools_v2.py -v
```

Expected: 0 failed。

- [ ] **Step 6: 提交多轮契约修复**

```powershell
git add tests/test_report_assistant_multiturn_e2e.py tests/test_report_assistant_api.py services/reporting/assistant/service.py routers/report_assistant.py
git commit -m "test: close assistant multi-turn contracts"
```

只添加实际修改的生产文件。

---

### Task 6: 创建可重复执行的申请风险 seed 与清理 SQL

**Files:**
- Create: `migrations/seeds/20260711_application_risk_acceptance.seed.sql`
- Create: `migrations/seeds/20260711_application_risk_acceptance.cleanup.sql`
- Create: `tests/test_report_assistant_seed_contract.py`

**Interfaces:**
- Consumes: `application_material_item` 和申请风险聚合器实际读取的其他事实表。
- Produces: A1024 高风险、A1058 中高风险、A1091 低风险的非敏感验收数据。

- [ ] **Step 1: 读取聚合器完整 SQL 和规则**

定位 `aggregate_application_risk()` 及其调用的规则函数，列出真正读取的表、字段、日期边界和 risk_items 纳入条件。不得根据任务书示例猜字段。

- [ ] **Step 2: 写 seed 契约 RED 测试**

```python
def test_seed_contains_three_synthetic_applications():
    sql = SEED.read_text(encoding="utf-8")
    assert {"A1024", "A1058", "A1091"}.issubset(set(extract_seed_ids(sql)))


def test_seed_is_idempotent_and_has_cleanup():
    sql = SEED.read_text(encoding="utf-8")
    cleanup = CLEANUP.read_text(encoding="utf-8")
    assert "ON DUPLICATE KEY UPDATE" in sql or "DELETE FROM" in sql
    assert all(app_id in cleanup for app_id in ("A1024", "A1058", "A1091"))
```

- [ ] **Step 3: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_seed_contract.py -v
```

Expected: FAIL，因为 seed 尚不存在。

- [ ] **Step 4: 编写 seed 和 cleanup**

使用聚合器真实字段，采用固定测试标识和事务。若 application_id 实际为 BIGINT，则使用 1024、1058、1091 存储，并在 SQL 注释/测试映射为 A1024、A1058、A1091。seed 先删除相同测试标识的旧数据再插入，cleanup 只删除这三个 ID 关联的本轮测试数据。

- [ ] **Step 5: 验证 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_assistant_seed_contract.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交 seed**

```powershell
git add migrations/seeds tests/test_report_assistant_seed_contract.py
git commit -m "test: add application risk acceptance seed"
```

---

### Task 7: 执行迁移、真实五步、403/404 与 LLM 验收

**Files:**
- Create: `docs/Claude code 完成报告/Iteration 2B.2 完成报告.md`（沿用现有交接目录名称）
- Modify only if needed: `.env.example`
- Modify only if needed: `.gitignore`

**Interfaces:**
- Consumes: 本地 `.env`、MySQL 8、FastAPI、版本化 migration/seed。
- Produces: 不含密钥和个人信息的真实验收证据。

- [ ] **Step 1: 审计 `.env` Git 安全**

```powershell
git check-ignore -v .env
git ls-files .env .env.example
git log --all --oneline -- .env
```

Expected: `.env` 被忽略、当前未跟踪。若历史 blob 含真实密钥，立即停止，报告需轮换密钥，不在输出中展示内容。

- [ ] **Step 2: 在隔离测试数据库验证 migration**

创建独立测试库，不对生产库做破坏性验证。依次执行：upgrade → `SHOW CREATE TABLE report_generation` → 应用启动/报告生成 smoke → downgrade → `SHOW CREATE TABLE` → upgrade。每步检查退出码，确认 status 和 trigger_source 契约。

- [ ] **Step 3: 加载 seed 并生成有风险明细的报告**

执行 seed 后，通过现有报告生成链路生成 application_risk，确认 `risk_items >= 2` 且最高项对应 A1024。若数据不满足，回到 Task 6 根据确定性规则修正 seed，不修改规则。

- [ ] **Step 4: 执行真实确定性五步**

使用同一登录会话和同一 context：

1. “看看现在的申请风险” → HTTP 202，记录 `R`。
2. “报告生成好了吗？” → assistant `query_report_status`，轮询到 completed。
3. “最严重的是哪几个？” → 至少两个 referenced_entities。
4. “第一个为什么这么高？” → entity_id 等于 Turn 3 position 1。
5. “这个风险分怎么算？” → 完整 MetricTrace。

记录生成前后任务数，断言 Turn 2-5 增量为 0，五步 report_id 唯一值数量为 1。

- [ ] **Step 5: 执行真实 403/404**

本地创建或重置受控 employee 账号，密码只放本地环境。验证 channel_roi、他人报告、psych_weekly 三种 403；使用 report_id 99999999 验证 assistant query_report_status 返回 404；伪造 application_id 不泄露其他报告内容。

- [ ] **Step 6: 执行真实 LLM explain_risk**

启用本地有效 LLM 配置，对同一 R 执行 drill_down、explain_risk、explain_metric。检查无 `{{E1}}` 残留、无 evidence 外核心数字、risk_score/risk reasons/entity_id 与报告一致、DataQuality 未弱化。再用受控无效模型或 Mock 网络错误验证确定性降级且不创建新报告。

- [ ] **Step 7: 清理 seed**

执行 cleanup SQL并确认只删除 A1024、A1058、A1091 对应测试数据。

- [ ] **Step 8: 写完成报告**

报告按任务书 21 项输出，所有账号、应用 ID（除合成 ID）、数据库连接和模型凭证脱敏。任何未通过项必须写实际错误和阻塞，不得写“建议通过”。

- [ ] **Step 9: 提交验收报告与必要配置样例**

```powershell
git add "docs/Claude code 完成报告/Iteration 2B.2 完成报告.md" .env.example .gitignore
git commit -m "docs: report iteration 2b2 acceptance"
```

只添加实际修改文件。

---

### Task 8: 完整回归与完成门禁

**Files:**
- No production changes expected.

**Interfaces:**
- Consumes: 所有本轮产物。
- Produces: 可复现的最终验证证据。

- [ ] **Step 1: 后端完整范围第一次运行**

```powershell
$assistantTests = Get-ChildItem tests -Filter 'test_report_assistant_*.py' | Sort-Object Name | ForEach-Object FullName
.\.venv\Scripts\python.exe -m pytest @assistantTests tests/test_reporting_v2_contracts.py tests/test_reporting_v2_rules.py tests/test_reporting_v2_ai_generator.py -v
```

Expected: 0 failed。

- [ ] **Step 2: 后端完整范围第二次运行**

重复同一命令。

Expected: 0 failed，证明无测试顺序污染。

- [ ] **Step 3: 前端完整测试**

```powershell
Set-Location frontend
npm test
```

Expected: 0 failed。

- [ ] **Step 4: 前端生产构建**

```powershell
Set-Location frontend
npm run build
```

Expected: exit 0，TypeScript 无错误。

- [ ] **Step 5: 检查 diff 和敏感信息**

```powershell
git diff --check
git status --short
git diff --name-only
git grep -n -I -E "REPORT_ASSISTANT_API_KEY=.+|DATABASE_PASSWORD=.+" -- ':!*.example'
```

Expected: 无新空白错误、`.env` 不出现、没有密钥值进入跟踪文件。

- [ ] **Step 6: 对照完成标准**

逐项核对 migration、upgrade/downgrade、risk entities、同一 report_id、assistant status、MetricTrace、真实 LLM、Evidence ID、前端重试、403、404、两次后端测试、前端测试/构建和 `.env` 安全。任一项没有证据则保持未完成状态。

