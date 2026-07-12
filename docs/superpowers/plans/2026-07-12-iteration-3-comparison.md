# Iteration 3 Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现由 Python 确定性计算的同类周期比较和白名单跨报告分析，并提供双周期 Evidence、DataQuality 与因果保护展示。

**Architecture:** Metric Catalog 声明 direct/derived/dimensional 指标，固定 resolver 负责提取，comparison 模块负责 Decimal 计算和质量门禁。Service 只编排周期、权限、工具与回答；前端只展示后端响应。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy、MySQL 8、pytest、React 19、TypeScript、Vitest。

## Global Constraints

- 禁止修改 `main.py`、`config.py`、`routers/__init__.py`、`models/report.py`、`services/reporting/rules.py`、`services/reporting/aggregators.py` 和原指标公式。
- 禁止 eval、动态 import、任意表达式、LLM 自定义路径/公式/resolver/工具循环。
- 比较请求只读，不创建 `report_generation`；任一报告无权限时整体 403 且无部分结果。
- `None` 不得转为 0；previous=0 时 change_rate=None；内部数值统一使用 Decimal。
- 单次请求最多 3 个业务工具；周期解析不计入。
- 新增/修改 Python 文件使用中文模块 docstring、函数 docstring 和关键逻辑注释。
- 已暴露密钥尚未轮换；任何代码、日志、测试、seed 和文档均不得包含真实密钥。

---

### Task 1: Comparison Schema Contract

**Files:**
- Modify: `services/reporting/assistant/schemas.py`
- Test: `tests/test_report_assistant_comparison_schemas.py`

**Interfaces:**
- Produces: `ComparisonPeriod`, `MetricComparison`, `ComparisonDataQuality`, `RelationshipSections`，以及扩展后的 `EvidenceItem`、`ReportAssistantMessageResponse`。

- [ ] **Step 1: Write failing schema tests**

```python
def test_metric_comparison_preserves_none_and_dimension():
    item = MetricComparison(
        report_type="channel_roi", metric_name="roi", label="ROI",
        dimension={"channel": "search"}, current_value=Decimal("-0.2"),
        previous_value=None, delta=None, change_rate=None, direction="unknown",
        unit="%", current_evidence_id="E1", previous_evidence_id="E2",
    )
    assert item.previous_value is None
    assert item.dimension == {"channel": "search"}

def test_evidence_accepts_comparison_binding():
    evidence = EvidenceItem(
        evidence_id="E1", label="本周高风险数", value=3, source_report_id=0,
        report_type="application_risk", period_label="本周",
        comparison_role="current", source_tables=["student_application"],
    )
    assert evidence.comparison_role == "current"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_comparison_schemas.py -v`
Expected: FAIL because comparison schemas/fields do not exist.

- [ ] **Step 3: Implement constrained Pydantic models**

```python
class ComparisonPeriod(BaseModel):
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    current_label: str
    previous_label: str
    assumptions: list[str] = Field(default_factory=list)

class MetricComparison(BaseModel):
    report_type: str
    metric_name: str
    label: str
    dimension: dict[str, str] = Field(default_factory=dict)
    current_value: Decimal | None
    previous_value: Decimal | None
    delta: Decimal | None
    change_rate: Decimal | None
    direction: Literal["up", "down", "flat", "unknown"]
    unit: str | None = None
    current_evidence_id: str
    previous_evidence_id: str

class RelationshipSections(BaseModel):
    confirmed_facts: list[str] = Field(default_factory=list)
    related_signals: list[str] = Field(default_factory=list)
    possible_explanations: list[str] = Field(default_factory=list)
    cannot_confirm: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_comparison_schemas.py -v`
Expected: PASS.

```bash
git add services/reporting/assistant/schemas.py tests/test_report_assistant_comparison_schemas.py
git commit -m "feat: add comparison response contracts"
```

### Task 2: Metric Catalog and Safe Resolvers

**Files:**
- Create: `services/reporting/assistant/metric_catalog.py`
- Create: `services/reporting/assistant/metric_resolvers.py`
- Create: `tests/test_report_assistant_metric_catalog.py`

**Interfaces:**
- Produces: `MetricDefinition`, `get_metric_definition()`, `list_metrics()`, `extract_metric_values()`。

- [ ] **Step 1: Write failing Catalog tests**

```python
def test_signed_count_uses_whitelisted_derived_resolver():
    definition = get_metric_definition("sales_funnel", "signed_count")
    assert definition.extraction_mode == "derived"
    assert definition.resolver_name == "funnel_stage_count"
    values = extract_metric_values(definition, {"funnel_counts": {"signed": 4}})
    assert values == [ExtractedMetric(value=Decimal("4"), dimension={})]

def test_channel_roi_is_dimensional():
    definition = get_metric_definition("channel_roi", "roi")
    values = extract_metric_values(definition, {
        "channel_metrics": [{"channel": "search", "roi": -0.2}]
    })
    assert values[0].dimension == {"channel": "search"}

def test_unknown_metric_rejected():
    with pytest.raises(ValueError, match="未注册指标"):
        get_metric_definition("sales_funnel", "invented")
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_metric_catalog.py -v`
Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement declarative Catalog and fixed dispatch**

```python
Resolver = Callable[["MetricDefinition", dict[str, Any]], list["ExtractedMetric"]]
RESOLVERS: dict[str, Resolver] = {
    "direct_path": resolve_direct_path,
    "funnel_stage_count": resolve_funnel_stage_count,
    "list_length": resolve_list_length,
    "dimension_list_value": resolve_dimension_list_value,
}

def extract_metric_values(definition: MetricDefinition, content: dict[str, Any]):
    resolver = RESOLVERS.get(definition.resolver_name or "")
    if resolver is None:
        raise ValueError(f"未注册 resolver: {definition.resolver_name}")
    return resolver(definition, content)
```

Use an explicit `METRIC_CATALOG: dict[tuple[str, str], MetricDefinition]`. Register
`application_risk.metrics.*`, derived funnel stage/list counts, dimensional
`channel_roi.channel_metrics.*`, and verified SLA/complaint overview keys. A key is omitted when
the corresponding test cannot extract it from the report content model.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_metric_catalog.py -v`
Expected: direct, derived, dimensional, None and sensitive permission cases PASS.

```bash
git add services/reporting/assistant/metric_catalog.py services/reporting/assistant/metric_resolvers.py tests/test_report_assistant_metric_catalog.py
git commit -m "feat: add controlled metric catalog"
```

### Task 3: Comparison Period Resolver

**Files:**
- Create: `services/reporting/assistant/comparison_period.py`
- Create: `tests/test_report_assistant_comparison_period.py`

**Interfaces:**
- Produces: `resolve_comparison_period(message, *, now, current_report_period=None) -> ComparisonPeriod`。

- [ ] **Step 1: Write fixed-date tests**

```python
NOW = datetime(2026, 7, 15, 10, 0)

def test_last_7_days_vs_previous_7_days():
    period = resolve_comparison_period("最近7天和前7天", now=NOW)
    assert (period.current_start, period.current_end) == (date(2026, 7, 9), date(2026, 7, 15))
    assert (period.previous_start, period.previous_end) == (date(2026, 7, 2), date(2026, 7, 8))

def test_this_month_uses_equal_elapsed_days():
    period = resolve_comparison_period("本月和上月", now=NOW)
    assert period.current_end == date(2026, 7, 15)
    assert period.previous_end == date(2026, 6, 15)
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_comparison_period.py -v`
Expected: FAIL because resolver does not exist.

- [ ] **Step 3: Implement explicit phrase parsing and invariants**

```python
def _validate_period_pair(period: ComparisonPeriod, today: date) -> None:
    if period.current_end > today or period.previous_end > today:
        raise ValueError("比较周期不能包含未来日期")
    if period.previous_end >= period.current_start:
        raise ValueError("比较周期不能重叠")
```

Implement branches for week, month-to-date, rolling 7/30 days, explicit Chinese months and
current-report/previous-period inside the new module; do not change `period_resolver.py`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_comparison_period.py -v`
Expected: all five required period cases PASS.

```bash
git add services/reporting/assistant/comparison_period.py tests/test_report_assistant_comparison_period.py
git commit -m "feat: resolve report comparison periods"
```

### Task 4: Decimal Calculation and DataQuality Gate

**Files:**
- Create: `services/reporting/assistant/comparison.py`
- Create: `tests/test_report_assistant_comparison.py`

**Interfaces:**
- Consumes: `ExtractedMetric`, `MetricDefinition`, two DataQuality dicts。
- Produces: `calculate_metric_comparison()` and `evaluate_comparison_quality()`。

- [ ] **Step 1: Write numeric and quality tests**

```python
def test_previous_zero_returns_none_rate():
    result = calculate_values(Decimal("5"), Decimal("0"), value_type="integer")
    assert result.delta == Decimal("5")
    assert result.change_rate is None

def test_percentage_has_point_delta_and_relative_rate():
    result = calculate_values(Decimal("0.30"), Decimal("0.20"), value_type="percentage")
    assert result.delta == Decimal("0.10")
    assert result.change_rate == Decimal("0.5")

def test_empty_blocks_trend():
    gate = evaluate_comparison_quality({"level": "empty"}, {"level": "ok"})
    assert gate.allow_values is True
    assert gate.allow_trend is False
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_comparison.py -v`
Expected: FAIL because calculation functions do not exist.

- [ ] **Step 3: Implement Decimal-only rules**

```python
def calculate_values(current: Decimal | None, previous: Decimal | None, *, value_type: str):
    if current is None or previous is None:
        return CalculatedValues(delta=None, change_rate=None, direction="unknown")
    delta = current - previous
    change_rate = None if previous == 0 else delta / abs(previous)
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return CalculatedValues(delta=delta, change_rate=change_rate, direction=direction)
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_comparison.py -v`
Expected: zero, None, precision, negative ROI, percentage and quality tests PASS.

```bash
git add services/reporting/assistant/comparison.py tests/test_report_assistant_comparison.py
git commit -m "feat: calculate deterministic metric comparisons"
```

### Task 5: Read-only Comparison Tool and Evidence

**Files:**
- Modify: `services/reporting/assistant/tools.py`
- Modify: `services/reporting/assistant/guardrails.py`
- Create: `tests/test_report_assistant_comparison_tool.py`

**Interfaces:**
- Produces: `tool_compare_report_metrics(*, report_type, comparison_period, metric_names, current_user, db) -> AssistantToolResult`。

- [ ] **Step 1: Write failing tool tests**

```python
def test_compare_prefers_completed_reports_and_creates_no_task(db_session, admin):
    before = db_session.query(ReportGeneration).count()
    result = tool_compare_report_metrics(
        report_type="application_risk", comparison_period=PERIOD,
        metric_names=["high_risk_count"], current_user=admin, db=db_session,
    )
    assert result.status == "success"
    assert db_session.query(ReportGeneration).count() == before
    assert [e["comparison_role"] for e in result.data["evidence"]] == [
        "current", "previous", "delta", "change_rate"
    ]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_comparison_tool.py -v`
Expected: FAIL because tool does not exist.

- [ ] **Step 3: Implement lookup → aggregate fallback → extraction → calculation**

```python
def _load_period_source(
    *, report_type: str, start: date, end: date,
    current_user: CurrentUser, db: Session,
) -> tuple[dict[str, Any], dict[str, Any], int, str]:
    report = query_completed_report(
        report_type=report_type, start=start, end=end, db=db,
    )
    if report is not None:
        _check_report_access(report, current_user)
        return report.report_content, report.data_quality, report.id, "report"
    aggregated = aggregate_report(report_type, db, start, end, {})
    return aggregated.content, aggregated.data_quality.model_dump(), 0, "aggregator"
```

Evidence IDs are allocated sequentially and include metric, dimension, period, role, formula and source tables.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_comparison_tool.py tests/test_report_assistant_answer_grounding.py -v`
Expected: tool, evidence uniqueness and no-report-creation tests PASS.

```bash
git add services/reporting/assistant/tools.py services/reporting/assistant/guardrails.py tests/test_report_assistant_comparison_tool.py
git commit -m "feat: compare report metrics read only"
```

### Task 6: Cross-report Catalog, Permissions and Tool Budget

**Files:**
- Create: `services/reporting/assistant/cross_report_catalog.py`
- Create: `tests/test_report_assistant_cross_report_catalog.py`

**Interfaces:**
- Produces: `CrossReportDefinition`, `get_cross_report_definition()`, `validate_cross_report_request()`。

- [ ] **Step 1: Write whitelist and fail-closed tests**

```python
def test_unregistered_pair_rejected():
    with pytest.raises(ValueError, match="未开放"):
        get_cross_report_definition("psych_weekly", "channel_roi")

def test_each_report_permission_checked_before_tools(monkeypatch):
    calls = []
    with pytest.raises(PermissionError):
        validate_cross_report_request(
            "channel_roi", "sales_funnel", role_code="employee",
            tool_call=lambda name: calls.append(name),
        )
    assert calls == []
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_cross_report_catalog.py -v`
Expected: FAIL because Catalog does not exist.

- [ ] **Step 3: Register four pairs with max_business_tool_calls <= 3**

```python
PAIR_KEY = frozenset[str]
CROSS_REPORT_CATALOG: dict[PAIR_KEY, CrossReportDefinition] = {
    frozenset(("complaint_weekly", "service_sla")): CrossReportDefinition(
        report_types=("complaint_weekly", "service_sla"),
        allowed_roles=("admin", "manager"), max_business_tool_calls=2,
        metric_bindings={"complaint_weekly": ("complaint_count",),
                         "service_sla": ("first_response_timeout_count", "resolution_timeout_count")},
        forbidden_claims=("导致", "证明", "必然", "根本原因是", "就是因为"),
    ),
    frozenset(("sales_funnel", "customer_ops")): CrossReportDefinition(
        report_types=("sales_funnel", "customer_ops"),
        allowed_roles=("admin", "manager", "employee", "team_leader"),
        max_business_tool_calls=2,
        metric_bindings={"sales_funnel": ("total_leads", "signed_count", "stagnant_lead_count"),
                         "customer_ops": ("total_leads",)},
        forbidden_claims=("导致", "证明", "必然", "根本原因是", "就是因为"),
    ),
    frozenset(("application_risk", "action_closure")): CrossReportDefinition(
        report_types=("application_risk", "action_closure"),
        allowed_roles=("admin", "manager"), max_business_tool_calls=2,
        metric_bindings={"application_risk": ("high_risk_count",),
                         "action_closure": ("overdue_count",)},
        forbidden_claims=("导致", "证明", "必然", "根本原因是", "就是因为"),
    ),
    frozenset(("channel_roi", "sales_funnel")): CrossReportDefinition(
        report_types=("channel_roi", "sales_funnel"),
        allowed_roles=("admin", "manager"), max_business_tool_calls=2,
        metric_bindings={"channel_roi": ("lead_count", "signed_count", "paid_amount", "roi"),
                         "sales_funnel": ("total_leads", "signed_count")},
        forbidden_claims=("导致", "证明", "必然", "根本原因是", "就是因为"),
    ),
}
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_cross_report_catalog.py -v`
Expected: whitelist, permission, no partial result and tool budget tests PASS.

```bash
git add services/reporting/assistant/cross_report_catalog.py tests/test_report_assistant_cross_report_catalog.py
git commit -m "feat: whitelist cross report analysis"
```

### Task 7: Relationship Answer and Causality Guardrail

**Files:**
- Modify: `services/reporting/assistant/answer_composer.py`
- Modify: `services/reporting/assistant/guardrails.py`
- Create: `tests/test_report_assistant_causality.py`

**Interfaces:**
- Produces: `compose_relationship_answer()` and `validate_causal_language()`。

- [ ] **Step 1: Write forbidden-claim and fallback tests**

```python
def test_llm_cannot_remove_causality_warning(monkeypatch):
    monkeypatch.setattr(ReportLLMClient, "chat_completion", fake_success("响应变慢导致投诉增加"))
    result = compose_relationship_answer(tool_results=RESULTS, llm_enabled=True)
    assert "不能证明" in result["relationship_sections"]["cannot_confirm"][0]
    assert "导致" not in result["answer"]

def test_template_has_all_four_sections():
    result = compose_relationship_answer(tool_results=RESULTS, llm_enabled=False)
    assert set(result["relationship_sections"]) == {
        "confirmed_facts", "related_signals", "possible_explanations", "cannot_confirm"
    }
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_causality.py -v`
Expected: FAIL because relationship composer does not exist.

- [ ] **Step 3: Implement four-section template and one repair attempt**

```python
FORBIDDEN_CAUSAL_PATTERNS = ("导致", "证明", "必然", "根本原因是", "就是因为")

def validate_causal_language(answer: str) -> list[str]:
    return [term for term in FORBIDDEN_CAUSAL_PATTERNS if term in answer]
```

Confirmed facts always come from Evidence; possible explanations always include uncertainty wording; cannot-confirm is inserted by Python after LLM output.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_causality.py tests/test_report_assistant_answer_grounding.py -v`
Expected: causal softening, fact preservation, warning retention and fallback tests PASS.

```bash
git add services/reporting/assistant/answer_composer.py services/reporting/assistant/guardrails.py tests/test_report_assistant_causality.py
git commit -m "feat: guard cross report causality"
```

### Task 8: Intent and Service Orchestration

**Files:**
- Modify: `services/reporting/assistant/schemas.py`
- Modify: `services/reporting/assistant/intent_parser.py`
- Modify: `services/reporting/assistant/service.py`
- Test: `tests/test_report_assistant_iteration3_service.py`

**Interfaces:**
- Consumes: Tasks 1-7 public functions。
- Produces: end-to-end handling for `compare_reports` and `cross_report_analysis`。

- [ ] **Step 1: Write service and HTTP behavior tests**

```python
def test_comparison_intent_creates_no_report(service, db, admin):
    before = db.query(ReportGeneration).count()
    response = service.handle_message(request=compare_request("本周申请风险和上周相比怎么样"), current_user=admin, db=db)
    assert response.intent == ReportAssistantIntent.COMPARE_REPORTS
    assert response.comparison
    assert db.query(ReportGeneration).count() == before

def test_cross_report_permission_returns_no_partial_data(client, employee_headers):
    response = client.post(URL, headers=employee_headers, json=cross_report_payload())
    assert response.status_code == 403
    body = response.json()
    assert body.get("evidence", []) == []
    assert body.get("comparison", []) == []
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_report_assistant_iteration3_service.py -v`
Expected: FAIL because service routes are not wired.

- [ ] **Step 3: Add deterministic keyword/LLM schema and orchestration branches**

```python
if plan.intent == ReportAssistantIntent.COMPARE_REPORTS:
    period = resolve_comparison_period(message, now=datetime.now())
    return [tool_compare_report_metrics(
        report_type=plan.report_type, comparison_period=period,
        metric_names=plan.focus_metrics, current_user=current_user, db=db,
    )]
if plan.intent == ReportAssistantIntent.CROSS_REPORT_ANALYSIS:
    definition = get_cross_report_definition(plan.report_types[0], plan.report_types[1])
    validate_all_permissions_before_execution(definition, current_user)
    return execute_cross_report_tools(definition, max_calls=3)
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_report_assistant_iteration3_service.py tests/test_report_assistant_multiturn_e2e.py -v`
Expected: same-report comparison, cross-report, 403, no partial result and no task creation PASS.

```bash
git add services/reporting/assistant/schemas.py services/reporting/assistant/intent_parser.py services/reporting/assistant/service.py tests/test_report_assistant_iteration3_service.py
git commit -m "feat: orchestrate iteration 3 analysis"
```

### Task 9: Frontend Comparison and Relationship Display

**Files:**
- Modify: `frontend/src/types/report-assistant.ts`
- Create: `frontend/src/components/report-assistant/ReportAssistantComparison.tsx`
- Create: `frontend/src/components/report-assistant/ReportAssistantRelationship.tsx`
- Modify: `frontend/src/components/report-assistant/ReportAssistantMessage.tsx`
- Modify: `frontend/src/components/report-assistant/ReportAssistantPanel.tsx`
- Test: `frontend/src/__tests__/report-assistant-iteration3.test.tsx`

**Interfaces:**
- Consumes: backend comparison and relationship fields exactly; performs no calculations。

- [ ] **Step 1: Write rendering and permission tests**

```tsx
it('renders backend comparison values and period labels', () => {
  render(<ReportAssistantComparison items={[comparison]} />)
  expect(screen.getByText('本周')).toBeInTheDocument()
  expect(screen.getByText('上周')).toBeInTheDocument()
  expect(screen.getByText('+2')).toBeInTheDocument()
})

it('hides partial analysis on permission error', () => {
  render(<ReportAssistantMessage message={permissionDeniedWithInjectedComparison} />)
  expect(screen.queryByText('变化率')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Verify RED**

Run: `cd frontend && npm run test:unit -- report-assistant-iteration3.test.tsx`
Expected: FAIL because components/types do not exist.

- [ ] **Step 3: Implement presentation-only components**

```tsx
if (message.status === 'permission_denied') return null
return <ReportAssistantComparison items={message.comparison ?? []} />
```

Map each backend item directly into table cells for metric, dimension, current, previous, delta,
changeRate and direction. Render four separate lists for the relationship section fields.

- [ ] **Step 4: Verify GREEN, build and commit**

Run: `cd frontend && npm run test:all && npm run build`
Expected: all tests and TypeScript/Vite build PASS.

```bash
git add frontend/src/types/report-assistant.ts frontend/src/components/report-assistant frontend/src/__tests__/report-assistant-iteration3.test.tsx
git commit -m "feat: display report comparisons"
```

### Task 10: MySQL Seed, Real Acceptance and Completion Report

**Files:**
- Create: `migrations/seeds/20260712_iteration3_comparison.seed.sql`
- Create: `migrations/seeds/20260712_iteration3_comparison.cleanup.sql`
- Create: `docs/Claude code 完成报告/Iteration 3 完成报告.md`
- Modify tests only if a real-environment defect is reproduced first.

**Interfaces:**
- Produces: repeatable two-period synthetic data and acceptance evidence。

- [ ] **Step 1: Add idempotent synthetic seed and cleanup**

Use reserved IDs `930001`-`930099` and marker prefix `ITER3_TEST_`. Seed two adjacent
periods with MySQL `INSERT IGNORE` guarded by reserved primary keys; include one rising count, one declining
count, one channel whose previous cost is zero and one missing optional channel value. Cleanup
uses both the reserved ID range and marker prefix so it cannot delete normal rows.

- [ ] **Step 2: Run real MySQL acceptance**

Execute `migrations/seeds/20260712_iteration3_comparison.seed.sql` against the configured
test database, then send these four requests:

```text
本周申请风险和上周相比怎么样？
最近两个周期哪个渠道表现变差了？
最近投诉增加是不是因为响应变慢了？
employee: 渠道 ROI 和销售转化一起分析
```

Expected: compare intent and Evidence periods are correct; channel values remain dimensional; causal answer has four sections; employee cross-report request is 403 with no partial result.

- [ ] **Step 3: Run real LLM smoke test with warning**

Before the call, remind that exposed credentials remain unrotated. Verify no naked core numbers, no unknown placeholders, no evidence swaps and no unsupported causal claim. On controlled API failure verify deterministic four-section fallback.

- [ ] **Step 4: Cleanup seed and run complete verification twice**

Backend command, twice:

```powershell
$assistantTests = Get-ChildItem tests -Filter 'test_report_assistant_*.py' | Sort-Object Name | ForEach-Object FullName
.\.venv\Scripts\python.exe -m pytest @assistantTests tests/test_reporting_v2_contracts.py tests/test_reporting_v2_rules.py tests/test_reporting_v2_ai_generator.py tests/test_integration_recovery.py -v -m "not llm_integration"
```

Frontend command:

```powershell
Set-Location frontend
npm run test:all
npm run build
```

Expected: two backend runs have 0 failed; frontend tests/build pass; cleanup query returns zero Iteration 3 seed rows.

- [ ] **Step 5: Write report, verify diff and commit**

Write the completion report with sections for supported and unsupported metrics, calculations,
quality, permissions, tool calls, Evidence, MySQL/LLM results, public-file changes (must be none),
security exception and known limits.

```powershell
git diff --check
git status --short
git add migrations/seeds docs/Claude` code` 完成报告/Iteration` 3` 完成报告.md
git commit -m "test: close iteration 3 acceptance"
```

## Final Verification Gate

- Run `git diff --check` and inspect every modified file against the allowed boundary.
- Confirm `git status --porcelain` is empty after the final commit.
- Confirm `.env` is ignored and not tracked.
- Do not push, start Iteration 4, or claim credential rotation.
