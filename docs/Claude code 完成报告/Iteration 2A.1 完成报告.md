# Iteration 2A.1 完成报告 — 多轮集成验证与证据绑定收口

**日期**：2026-07-11
**分支**：Berlin
**基线**：178 passed, 2 skipped → **257 passed, 2 skipped**

---

## 1. 完整多轮 E2E 测试采用的数据库或 Mock 方案

**采用方案：Mock Repository（方案 2）**

原因：
- `ReportGeneration` 使用 `BIGINT(unsigned=True)` 主键，SQLite 不支持其 autoincrement
- Mock `_execute_tool` 在 Service 层拦截，覆盖完整编排链（意图解析 → 澄清判断 → 工具调用 → 回答生成 → 上下文更新）
- 不依赖真实数据库，避免 SQLite 兼容性问题
- 可精确控制各轮工具返回数据

测试文件：`tests/test_report_assistant_multiturn_e2e.py`（15 个测试）

---

## 2. 四轮请求和响应流

```
Turn 1: "看看现在的申请风险"
  → intent: GENERATE_REPORT
  → status: generating
  → report_id: 128
  → context: { last_report_id: 128, last_report_type: "application_risk" }

Turn 2: "最严重的是哪几个？"
  → intent: DRILL_DOWN
  → status: completed
  → context: { last_report_id: 128, referenced_entities: [
      {position:1, entity_id:"A1024", risk_score:90},
      {position:2, entity_id:"A1058", risk_score:70}
    ] }

Turn 3: "第一个为什么这么高？"
  → intent: EXPLAIN_RISK
  → status: completed
  → "第一个" → resolve_entity_reference → A1024
  → 回答包含 A1024 的风险原因（逾期、缺少材料）
  → 不包含 A1058 的风险原因

Turn 4: "这个风险分怎么算？"
  → intent: EXPLAIN_METRIC
  → status: completed
  → 返回 MetricTrace: source_tables=["application_risk_fact"],
    formula="base_score + overdue_bonus + missing_material_bonus"
```

---

## 3. report_id 是否始终一致

✅ **是。**四轮中 `last_report_id` 始终为 `128`（FIXED_REPORT_ID）。验证测试：`test_report_id_consistent_across_four_turns`。

---

## 4. 是否发生重复生成

✅ **否。**Turn 2（drill_down）不会调用 `create_report_task_result()`。验证测试：`test_turn2_drill_down_does_not_regenerate` — 确认 `_execute_tool` 只被调用一次，且 intent 为 `DRILL_DOWN`。

---

## 5. referenced_entities 如何传递

1. Turn 2 工具 `tool_get_application_risk_items` 返回 `referenced_entities` 列表
2. Service 层 Step 7 从工具结果提取并写入 `updated_context.referenced_entities`
3. 前端在下一轮请求中传回 `conversation_context`
4. Turn 3 中 `resolve_entity_reference(message="第一个为什么这么高？", context=...)` 解析出 A1024
5. 跨 Service 实例时，上下文通过 `ReportConversationContext` Pydantic 对象传递，无进程内状态依赖

---

## 6. 客户端伪造上下文测试结果

| 测试 | 结果 | 说明 |
|------|------|------|
| `test_forged_report_id_is_denied` | ✅ | 伪造 report_id=99999 → 工具返回 "报告不存在" |
| `test_forged_entity_id_is_rejected` | ✅ | 伪造 entity_id="FAKE999" → 工具返回 "未找到申请" |
| `test_entity_from_other_report_is_rejected` | ✅ | source_report_id=999 ≠ last_report_id=128 → 拒绝 |
| `test_entity_position_out_of_range` | ✅ | "第三个" 但只有 2 个实体 → 返回错误 |
| `test_other_employee_report_cannot_be_read` | ✅ | employee 角色访问他人报告 → 权限拒绝 |
| `test_unauthorized_psych_report_context` | ✅ | employee 访问 psych_weekly → 权限拒绝 |
| `test_client_metadata_not_trusted` | ✅ | 客户端传入 risk_score=999，工具返回真实值 90 |

**核心原则**：客户端 `metadata` 中的 `risk_score`、`risk_level`、`display_name` 全部不可信。最终业务值必须重新从报告内容读取。

---

## 7. EvidenceItem 最终结构

```python
class EvidenceItem(BaseModel):
    evidence_id: str = ""           # 证据占位符 ID，如 E1、E2
    entity_type: Optional[str]      # 实体类型，如 application
    entity_id: Optional[str]        # 实体 ID，如 A1024
    metric_name: Optional[str]      # 指标名称，如 risk_score
    label: str = ""                 # 人类可读标签，如 "申请 A1024 风险分"
    value: Any = None               # 引用值（原始类型）
    unit: Optional[str]             # 单位，如 分、%、元、天
    source_report_id: int = 0       # 来源报告 ID
    source_tables: list[str] = []   # 数据来源表
    formula: Optional[str]          # 指标计算公式
    source: str = ""                # 来源工具名（向后兼容）
    reference: str = ""             # 数据路径（向后兼容）
```

示例：
```json
{
  "evidence_id": "E1",
  "entity_type": "application",
  "entity_id": "A1024",
  "metric_name": "risk_score",
  "label": "申请 #A1024 风险分",
  "value": 90,
  "unit": "分",
  "source_report_id": 128,
  "source_tables": ["application_risk_fact"],
  "formula": "base_score + overdue_bonus + missing_material_bonus"
}
```

---

## 8. 证据占位符绑定方案

**采用方案 A：证据占位符**

```
工具结果 → build_structured_evidence() → EvidenceItem 列表
         → build_evidence_map_structured() → {E1: EvidenceItem, E2: ...}
         → LLM Prompt 含证据索引 + 强制占位符规则
         → LLM 输出 "申请 A1024 风险分为 {{E1}}，共 {{E2}} 个高风险"
         → replace_evidence_placeholders() → "申请 A1024 风险分为 90 分，共 8 个"
         → validate_evidence_binding() → 校验 evidence_id 合法性
         → validate_numbers_in_answer() → 第二层数字兜底校验
```

**LLM 必须遵守的规则**（写入 System Prompt）：
1. 所有业务数字必须使用 `{{E1}}` `{{E2}}` 占位符引用
2. 禁止直接写风险分、ROI、CPL、CAC、SLA 超时数、转化率等具体数值
3. 每个占位符有固定含义（E1=申请 A1024 风险分=90），不能交换使用

---

## 9. 数字与实体错配如何拦截

**第一层：证据占位符校验**
- `validate_evidence_binding()` 提取 LLM 回答中的 `{{Ex}}` 引用
- 检查所有 evidence_id 是否在证据映射中存在
- 未知 evidence_id → 记录错误，替换为 `[未知证据 {{E99}}]`

**第二层：裸业务数字检测**
- `_check_naked_business_numbers()` 在占位符替换前检查 LLM 原始回答
- 如果 LLM 绕过占位符直接写了业务数字（如 "风险分为 90"）→ 触发一次修复重试
- 修复仍失败 → 确定性模板降级

**第三层：数字校验器兜底**
- 替换后的最终回答中所有数字必须在 `allowed_numbers` 集合中
- 超出范围的数字 → 如果是明确的业务数字幻觉 → 降级到模板
- 日期/ID 等非业务数字自动跳过

**示例**：
- 工具证据：`E1=A1024 risk_score=90`, `E2=high_risk_count=8`
- 模型输出 "A1024 风险分为 {{E2}}" → `replace_evidence_placeholders` 替换为 "A1024 风险分为 8 个" → 虽然数字合法（8 在 allowed_numbers 中），但实体-指标绑定错误
- 当前版本依赖 Prompt 约束防止此类错配；更严格的语义检查留待后续迭代

---

## 10. 裸业务数字如何处理

1. LLM 原始回答在占位符替换前 → `_check_naked_business_numbers()` 检测
2. 如果值匹配证据中的数字且未用 `{{Ex}}` 包裹 → 标记为 `has_naked=True`
3. 自动发起一次修复重试（temperature=0.1），要求 LLM 改用占位符
4. 修复后再次检测 → 仍失败 → 确定性模板降级

**不被误判的数字**：
- 日期格式（2026-07-11）→ 预处理移除
- 中文序号（第一、第二）→ 预处理移除
- 4 位及以上整数 ID → 预处理移除
- 非证据值集合内的数字（如序号 1, 2, 3）→ 不匹配，不触发

---

## 11. 工具专项测试清单

| 工具 | 测试 | 状态 |
|------|------|------|
| **报告状态** | `test_status_pending` | ✅ |
| | `test_status_generating` | ✅ |
| | `test_status_completed` | ✅ |
| | `test_status_failed_suggests_retry` | ✅ |
| | `test_status_not_found` | ✅ |
| | `test_status_permission_denied` | ✅ |
| **报告详情** | `test_detail_requires_completed_report` | ✅ |
| | `test_detail_returns_schema_version` | ✅ |
| | `test_detail_returns_metric_traces` | ✅ |
| | `test_detail_does_not_return_html` | ✅ |
| | `test_detail_sanitizes_psych_content` | ✅ |
| | `test_detail_checks_row_permission` | ✅ |
| **风险列表** | `test_risk_items_sorted_descending` | ✅ |
| | `test_risk_items_filter_by_level` | ✅ |
| | `test_risk_items_limit_max_ten` | ✅ |
| | `test_risk_items_generate_correct_positions` | ✅ |
| | `test_risk_items_do_not_trust_client_metadata` | ✅ |
| **风险详情** | `test_risk_detail_returns_exact_entity` | ✅ |
| | `test_risk_detail_not_found` | ✅ |
| | `test_risk_detail_reasons_are_not_generated` | ✅ |
| | `test_risk_detail_rejects_entity_from_other_report` | ✅ |
| **MetricTrace** | `test_metric_alias_resolves_to_registered_metric` | ✅ |
| | `test_unknown_metric_is_rejected` | ✅ |
| | `test_metric_trace_returns_source_formula_filters` | ✅ |
| | `test_metric_trace_does_not_allow_jsonpath` | ✅ |
| | `test_metric_trace_does_not_allow_table_name_input` | ✅ |
| **DataQuality** | `test_warning_keeps_answer_and_adds_limitation` | ✅ |
| | `test_empty_replaces_analysis_with_no_data_message` | ✅ |
| | `test_degraded_blocks_strong_conclusion` | ✅ |
| | `test_failed_blocks_business_analysis` | ✅ |
| | `test_ok_has_no_limitations` | ✅ |
| | `test_llm_cannot_remove_quality_warning` | ✅ |
| **内部辅助** | `test_safe_error_message_truncates` | ✅ |
| | `test_safe_error_message_handles_none` | ✅ |
| | `test_sanitize_psych_preserves_non_sensitive` | ✅ |
| | `test_sanitize_psych_handles_non_dict` | ✅ |

测试文件：`tests/test_report_assistant_tools_v2.py`（35 个测试）

---

## 12. DataQuality 测试结果

| 等级 | 约束 | 测试 | 结果 |
|------|------|------|------|
| `ok` | 无限制 | `test_ok_has_no_limitations` | ✅ |
| `warning` | 必须说明数据局限性 | `test_warning_keeps_answer_and_adds_limitation` | ✅ |
| `empty` | 不得解释趋势、不得分析变化原因 | `test_empty_replaces_analysis_with_no_data_message` | ✅ |
| `degraded` | 不得给出强结论、必须说明降级原因 | `test_degraded_blocks_strong_conclusion` | ✅ |
| `failed` | 不得生成业务分析、不得做趋势判断 | `test_failed_blocks_business_analysis` | ✅ |

**关键约束**：
- `warning` + `is_analysis=True` → 前缀注入（保留原始回答）
- `empty` / `failed` + `is_analysis=True` → 只返回限制文本（原始分析内容不出现）
- LLM 无法通过 Prompt 绕过或移除 DataQuality 限制 — 注入发生在 Python 层

---

## 13. Answer Composer 测试结果

| 测试 | 结果 |
|------|------|
| `test_build_structured_evidence_extracts_risk_scores` | ✅ |
| `test_build_evidence_map_structured_keys` | ✅ |
| `test_empty_tool_data_returns_empty` | ✅ |
| `test_replace_known_evidence_ids` | ✅ |
| `test_unknown_evidence_id_is_rejected` | ✅ |
| `test_placeholder_without_unit` | ✅ |
| `test_naked_business_number_is_detected` | ✅ |
| `test_placeholder_answer_passes_naked_check` | ✅ |
| `test_non_business_numbers_not_flagged` | ✅ |
| `test_valid_binding_passes` | ✅ |
| `test_evidence_entity_mismatch_is_rejected` | ✅ |
| `test_evidence_metric_mismatch_is_detected` | ✅ |
| `test_date_not_flagged_as_business_number` | ✅ |
| `test_percentage_handled` | ✅ |
| `test_decimal_handled` | ✅ |
| `test_negative_number_handled` | ✅ |
| `test_thousands_separator_handled` | ✅ |
| `test_90_vs_90_float_equivalent` | ✅ |
| `test_ordinal_not_flagged` | ✅ |
| `test_llm_disabled_uses_template` | ✅ |
| `test_template_answer_uses_exact_tool_values` | ✅ |
| `test_llm_failure_uses_template` | ✅ |
| `test_compose_answer_generic_fallback` | ✅ |
| `test_warning_adds_prefix_to_analysis` | ✅ |
| `test_empty_replaces_analysis` | ✅ |
| `test_failed_blocks_analysis` | ✅ |
| `test_ok_status_no_change` | ✅ |

测试文件：`tests/test_report_assistant_answer_grounding.py`（27 个测试）

---

## 14. 修改文件清单

### 源代码修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/reporting/assistant/schemas.py` | 修改 | `EvidenceItem` 增强为五元绑定模型（entity_type/entity_id/metric_name/label/value/unit/source_report_id/source_tables/formula） |
| `services/reporting/assistant/guardrails.py` | 重写 | 新增 `build_structured_evidence()`、`build_evidence_map_structured()`、`replace_evidence_placeholders()`、`validate_evidence_binding()`；重写 `validate_numbers_in_answer()` 修正日期/百分比/小数/货币/负数/千位分隔符边界 |
| `services/reporting/assistant/answer_composer.py` | 重写 | 实施证据占位符方案 A：LLM 必须使用 `{{E1}}` 占位符 → Python 替换 + 校验 → 裸数字检测 → 绑定校验 → 数字第二层校验 → 确定性模板降级 |
| `services/reporting/assistant/service.py` | 修改 | `_execute_tool` 新增 `message` 参数用于实体引用解析；Step 4 时间解析对多轮追问意图放行；Step 3 澄清逻辑适配多轮意图 |
| `services/reporting/assistant/clarification.py` | 修改 | `decide_clarification()` 对多轮追问意图（drill_down/explain_risk 等）不需 report_type 也可通过置信度检查 |
| `services/reporting/assistant/intent_parser.py` | 修复 | 移除 `_detect_multi_turn_intent_keywords` 中不可达的 `return days[weekday]` 代码 |

### 测试文件新增

| 文件 | 操作 | 测试数 |
|------|------|--------|
| `tests/test_report_assistant_multiturn_e2e.py` | **新增** | 15 |
| `tests/test_report_assistant_tools_v2.py` | **新增** | 35 |
| `tests/test_report_assistant_answer_grounding.py` | **新增** | 27 |

### 测试文件修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `tests/test_report_assistant_service.py` | 修改 | mock `_execute_tool` 签名添加 `message=""` 参数 |

### 未修改文件（遵守修改边界）

`routers/__init__.py`、`main.py`、`config.py`、`models/report.py`、`services/reporting/orchestrator.py`、`services/reporting/aggregators.py`、`services/reporting/rules.py`、`services/reporting/ai_generator.py`、所有前端文件。

---

## 15. 唯一测试统计

```bash
pytest \
  tests/test_report_assistant_*.py \
  tests/test_reporting_v2_contracts.py \
  tests/test_reporting_v2_rules.py \
  tests/test_reporting_v2_ai_generator.py \
  -v
```

| 指标 | Iteration 2A | Iteration 2A.1 | 增量 |
|------|-------------|----------------|------|
| collected | 180 | **259** | +79 |
| passed | 178 | **257** | +79 |
| skipped | 2 | **2** | 0 |
| failed | 0 | **0** | 0 |

### 独立运行

```bash
pytest tests/test_report_assistant_multiturn_e2e.py -v
# 15 passed

pytest tests/test_report_assistant_answer_grounding.py -v
# 27 passed

pytest tests/test_report_assistant_tools_v2.py -v
# 35 passed
```

---

## 16. 已知限制

1. **语义级实体-指标绑定校验**：当前 validate_evidence_binding() 检查 evidence_id 合法性，但不做 "{{E2}} 不能用于表示 A1024 的 risk_score" 这类语义级检查。这依赖 Prompt 约束。更强的语义校验需要 LLM 输出结构化 Claim 而非自由文本（方案 B）。

2. **证据占位符仅在 LLM 模式下生效**：确定性模板直接使用工具数据中的数值，不通过占位符流程。

3. **MetricTrace 中的 formula 字段**：当前作为字符串直接返回，不校验其内容是否真的是公式还是 LLM 编造。但公式来自报告内容（`report_content.metric_traces`），由聚合器预计算，LLM 不直接接触。

4. **多轮意图仅支持 application_risk**：其他报告类型（sales_funnel/channel_roi）的 drill_down/explain_risk 工具调用需要在后续迭代中扩展。

5. **E2E 测试使用 Mock Repository**：未在真实 MySQL 数据库中端到端验证完整四轮对话。前端集成验收建议在 Iteration 2B 中进行。

---

## 17. 是否建议进入 Iteration 2B

**建议进入 Iteration 2B（前端最小对话面板）。**

Iteration 2A.1 已完成的安全收口：
- ✅ 完整四轮后端多轮链路集成测试（15 个 E2E 测试）
- ✅ 客户端上下文伪造安全性验证（7 个安全测试）
- ✅ 证据占位符强制绑定（两层保护：占位符 + 数字校验）
- ✅ 工具专项测试全覆盖（35 个测试，6 个工具 × 内部辅助）
- ✅ Answer Composer 证据绑定测试（27 个测试）
- ✅ DataQuality 约束不可被 LLM 绕过
- ✅ LLM 失败确定性模板可用
- ✅ 257 测试全部通过，零回归
- ✅ 未修改公共文件和数据库表

Iteration 2B 建议范围：
- `frontend/src/pages/` 中新增最小对话面板组件
- `frontend/src/api/` 中新增 `report-assistant.ts` API 层
- 复用现有 `POST /api/v1/reports/assistant/messages` 接口
- 展示对话历史、证据卡片、建议追问按钮
- 端到端验收四轮完整对话（含真实 MySQL 数据）
