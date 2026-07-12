# Iteration 3 周期对比与受控跨报告分析设计

## 1. 状态与目标

Iteration 2B.2 已由提交 `6e46aa0` 独立收口，公共文件 Diff 已审查，`.env` 未被
Git 跟踪，工作区在本设计开始前干净。已暴露密钥尚未轮换；这是用户明确接受的
临时例外，不能表述为前置条件已满足，真实 LLM 验收前必须再次提示。

本轮让用户通过自然语言比较同类报告的两个周期，并在预注册范围内联合分析两类
报告。所有指标提取、差值、变化率、方向和 DataQuality 判断由 Python 完成；LLM
只基于 Evidence 归纳，不计算指标、不选择任意字段，也不能声明未经证明的因果关系。

## 2. 范围边界

实现同类周期比较、受控跨报告组合、双周期 DataQuality、工具调用上限、四区关系
回答、前端最小展示、MySQL seed/cleanup 和真实 LLM 验收。不实现 Redis、会话持久化、
NL2SQL、自由组合、自动异常检测、行动项写入、多 Agent、RAG 或新业务表。

不修改 `main.py`、`config.py`、`routers/__init__.py`、`models/report.py`、
`services/reporting/rules.py`、`services/reporting/aggregators.py` 和原指标公式。发现必须
突破边界时停止并说明。

## 3. 总体架构

采用分层目录与确定性工具链：

```text
用户问题
→ 意图识别
→ ComparisonPeriod 解析
→ Metric/Cross-report Catalog 白名单
→ 所有报告权限预检
→ completed 报告读取或只读 Aggregator
→ direct/derived/dimensional resolver
→ Decimal 比较计算
→ 双周期 DataQuality 联合判断
→ current/previous/delta/change_rate Evidence
→ 四区因果保护
→ LLM 归纳
→ Python 最终校验
→ 前端只读展示
```

新增 `COMPARE_REPORTS` 与 `CROSS_REPORT_ANALYSIS`。不新增重复的关系解释意图。

## 4. Metric Catalog 与受控派生指标

`metric_catalog.py` 只保存声明式元数据，`metric_resolvers.py` 通过固定字典分发实现
提取。禁止 `eval`、任意 Python 表达式、动态 import，以及由 LLM 指定路径、公式、
resolver 或聚合方式。

`MetricDefinition` 至少包含：

```python
report_type: str
metric_name: str
label: str
extraction_mode: Literal["direct", "derived", "dimensional"]
value_path: tuple[str, ...] | None
source_fields: tuple[tuple[str, ...], ...]
resolver_name: str | None
dimension_name: str | None
dimension_key: str | None
value_type: Literal["integer", "decimal", "percentage", "duration", "currency"]
unit: str | None
allow_delta: bool
allow_change_rate: bool
sensitive: bool
none_semantics: str
zero_denominator_rule: Literal["not_applicable", "return_none"]
data_quality_rule: Literal["inherit", "warning_on_missing"]
```

- `direct` 使用固定真实路径。
- `derived` 使用白名单 resolver，例如 `signed_count ← funnel_counts["signed"]`、
  `stagnant_lead_count ← len(stalled_leads)`。
- `dimensional` 从列表按明确维度提取；渠道 ROI 按 channel 分行，禁止压缩成报告级 ROI。
- 每个派生指标声明来源、resolver、类型、单位、None 语义、零分母和质量规则。
- 无法直接读取或可靠派生的指标不注册，在完成报告记录差距。

Catalog 契约测试验证路径、resolver、权限敏感性和真实 Schema 可提取性。

## 5. 周期模型

新增 `ComparisonPeriod`：

```python
current_start: date
current_end: date
previous_start: date
previous_end: date
current_label: str
previous_label: str
assumptions: list[str]
```

规则：

- 本周/上周均为完整自然周；
- 本月截至当前日，上一周期取上月相同日数；
- 最近 7/30 天包含今天，前一周期紧邻且不重叠；
- 明确自然月按完整日历月，允许天数不同；
- 当前报告与上一期按当前报告长度向前平移；
- 隐含规则进入 assumptions；非用户明确要求时禁止未来周期和重叠周期。

现有单周期解析器行为不变，测试使用固定 `now`。

## 6. 数据获取与比较计算

每个周期先查相同 `report_type + period_start + period_end + completed` 报告；多条时按
`update_time/create_time/id` 选择最新。无报告则调用现有 `aggregate_report()` 只读聚合，
不创建 `report_generation`。

两份报告分别鉴权。跨报告在读取指标前完成全部权限预检；任一无权限则整个请求 403，
无 evidence、无部分结果、无敏感 report_type。

内部计算统一使用 `Decimal`：

```text
delta = current - previous
change_rate = (current - previous) / abs(previous)
```

- `None` 保持 `None`；
- previous=0 时仍计算 delta，但 change_rate=None；
- 百分比 delta 表示百分点差，change_rate 表示相对变化；
- 负 ROI 使用 `abs(previous)`；
- dimensional 指标按每个 channel 分别计算；
- JSON 响应阶段才转换成可序列化表示。

## 7. 双周期 DataQuality

current 与 previous 分别保留来源和 DataQuality：

- `ok + ok`：完整比较；
- 任一 warning：保留计算并明确限制；
- 任一 empty/failed：不产生 delta、change_rate、direction；
- 任一 degraded：展示两个原值，只给有限趋势；
- Schema 版本、指标定义或周期口径不兼容：拒绝直接比较。

不得用一个周期质量覆盖另一个周期。

## 8. 受控跨报告组合与工具上限

`cross_report_catalog.py` 按无序报告对匹配，输出顺序固定。首期仅注册：

- complaint_weekly + service_sla；
- sales_funnel + customer_ops；
- application_risk + action_closure；
- channel_roi + sales_funnel。

每个组合定义角色、可靠指标绑定、周期模式、最大业务工具数、禁止结论和输出模板。
缺少可靠指标时只注册可证明部分并记录差距。

单次请求最多 3 个业务工具，周期解析不计入。LLM 不能循环调用工具；超限、未注册组合
或指标不足时返回具体澄清。

## 9. Evidence 与因果保护

每个“指标”或“指标 + 维度”生成四种独立 Evidence：current、previous、delta、
change_rate。Evidence 增加 `period_label`、`comparison_role`、`report_type`、`dimension`，
并保留单位、公式、来源表与 DataQuality 限制。当前和上一周期证据不能交换。

跨报告回答固定为：已确认事实、相关信号、可能解释、无法确认。Python 最终校验禁止
未限定的“导致、证明、必然、根本原因是、就是因为”。LLM 删除因果警告、交换证据、
输出裸业务数字或未知证据时只修复一次；仍不合格则使用四区确定性模板。

## 10. Service 与响应契约

Service 负责意图、周期、Catalog、权限、工具上限、质量、Evidence 与回答编排，不把
计算委托给 LLM。响应新增：

- `comparison`：指标、维度、两期值、delta、change_rate、direction、周期标签；
- `current_data_quality`、`previous_data_quality`；
- `relationship_sections`：四区内容；
- 扩展后的 Evidence。

比较默认只读，不使用生成报告幂等键，也不新增报告记录。

## 11. 前端

仅修改现有助手消息面板：

- 对比表显示指标、维度、当前、上一期、差值、变化率和方向；
- 渠道按 channel 分行；
- 关系分析显示四个明确分区；
- 403 不渲染部分结果；
- TypeScript 不计算任何指标、差值、变化率或方向。

## 12. 测试与真实验收

按 TDD 覆盖 Metric Catalog/resolver、周期、Decimal/零分母/负 ROI/百分点/None、双周期
DataQuality、跨报告白名单和逐报告鉴权、工具上限、Evidence 绑定、因果保护、Service、
HTTP 403 与前端展示。

MySQL seed/cleanup 提供两个周期，至少包含上升、下降、previous=0 和 None，且不使用真实
个人数据。真实验收覆盖申请风险对比、渠道维度 ROI、投诉 + SLA、越权、DataQuality 和
真实 LLM 因果保护。结束后清理 seed。

后端完整测试连续两轮 0 failed，前端测试和构建通过。完成后停止，不进入 Iteration 4。

## 13. 已知安全例外

已暴露的 LLM 与数据库密钥尚未轮换。用户决定暂不轮换并继续开发。本设计与后续代码、
日志、命令和报告不得记录密钥；在真实外部服务验收及任何推送前必须再次提示轮换风险。
