# Iteration 2B.2 完成报告

## 1. 结论

Iteration 2B.2 已完成真实多轮闭环、测试隔离、数据库迁移、前端重试幂等、权限与异常验收。当前不进入 Iteration 3。

## 2. 数据库迁移

- Upgrade：`migrations/20260711_01_sync_report_generation_contract.up.sql`
- Downgrade：`migrations/20260711_01_sync_report_generation_contract.down.sql`
- 契约测试：`tests/test_report_assistant_database_contract.py`
- 技术债：`docs/智能报告助手_数据库枚举技术债.md`

在独立 MySQL 8 测试库 `education_service_iter2b2_test` 实测：

1. upgrade 后 `report_type=VARCHAR(64)`，`status=ENUM(pending,generating,completed,failed)`，`trigger_source=ENUM(manual,schedule,retry,system)`；
2. downgrade 后三个字段分别恢复为 `VARCHAR(64)`、`VARCHAR(32)`、`VARCHAR(16)`；
3. 再次 upgrade 成功；
4. 业务库升级前完成非法旧值检查，未发现非法状态；升级已成功执行。

## 3. 测试 Seed

- Seed：`migrations/seeds/20260711_application_risk_acceptance.seed.sql`
- Cleanup：`migrations/seeds/20260711_application_risk_acceptance.cleanup.sql`
- 合成申请：A1024、A1058、A1091，对应测试 application_id 1024、1058、1091。
- 验收报告中 A1024 风险分 80，触发三项规则；A1058 风险分 45，触发三项规则。
- 验收结束后已执行 cleanup：匹配种子材料由 4 行清理为 0 行。

## 4. 真实五步闭环

五步唯一报告 ID：`7`。生成前后 `report_generation` 数量从 6 变为 7，总增量为 1；Turn 2-5 没有新增报告。

| 轮次 | 请求与结果 | 核心验收 |
| --- | --- | --- |
| Turn 1 | 生成申请风险报告，HTTP 202，`generating` | `report_id=7` |
| Turn 2 | 助手内发送“报告生成好了吗？”，HTTP 200，`query_report_status` | `completed`，仍为 7 |
| Turn 3 | “最严重的是哪几个？”，`drill_down` | 实体 1024、1058；证据 E1、E2；position 1 为 1024 |
| Turn 4 | “第一个为什么这么高？”，`explain_risk` | entity_id=1024；原因来自原报告，不信任客户端 metadata |
| Turn 5 | “这个风险分怎么算？”，`explain_metric` | entity 保持一致；MetricTrace 证据 E1，包含来源表、公式、过滤条件和周期 |

强制断言结果：五步 report_id 唯一值数量为 1；Turn 3 实体数为 2；Turn 4 命中 Turn 3 position 1；Turn 2-5 新增记录为 0。

## 5. 真实 LLM 与降级

真实 LLM 三轮使用同一报告 7：

- drill_down：`completed`，实体 1024/1058，证据 E1/E2；
- explain_risk：`completed`，证据 E1/E2；
- explain_metric：`completed`，证据 E1；
- 三轮均无未替换 `{{E...}}`，DataQuality 为数据库来源；最终运行日志无模板降级警告。

真实验证期间发现并修复：普通回答错误携带 JSON mode、模型可选字段返回 null、多轮计划未继承上下文报告 ID、Markdown 列表序号被误判为业务数字、模型引用不存在证据 ID。网络超时 Mock 也验证了确定性模板降级，且不会重复创建报告。

本次实际验收模型为本地现有安全配置中的 `deepseek-chat`。密钥没有写入代码、测试或本报告。

## 6. MetricTrace evidence

`build_structured_evidence()` 现兼容 metric trace 列表和工具顶层结果，每条证据生成稳定、唯一的 E1/E2 编号，并保留 `metric_name`、`source_report_id`、`source_tables`、`formula`、`filters/reference`。相关占位符替换和未知证据拒绝测试已通过。

## 7. 前端重试幂等

用户消息保存 `clientRequestId` 与 `originalRequest`。错误重试复用原 message、原 context 快照和原 client_request_id；新消息和建议追问继续生成新 ID；发送期间阻止重复点击。相关面板测试通过。

## 8. 403 与 404

- employee 请求 `channel_roi`：HTTP 403，`permission_denied`，无 evidence，不返回敏感 report_type；
- employee 请求 `psych_weekly`：HTTP 403，无学生字段；
- employee A 查询 employee B 报告：HTTP 403；
- report_id 99999999 查询状态：HTTP 404，`not_found`，意图为 `query_report_status`，无新增报告；
- 工具层不存在实体返回 not_found/安全澄清，不泄漏其他报告内容。

## 9. 测试隔离与路由收口

- 测试入口强制关闭真实助手 LLM，真实 LLM 用例自行显式开启；
- SQLite 测试元数据对 MySQL 允许的跨表同名索引进行测试进程内唯一化；
- 环境设置、依赖覆盖和数据库事务由 fixture 管理；
- 合并覆盖后恢复 V2 报告路由，并把旧日报拆到 `routers/daily_report.py`；
- OpenAPI 同时存在 `/api/v1/reports/*`、`/api/v1/reports/assistant/messages` 和旧日报 `/api/v1/report/*`；
- 前端 operation catalog 已与 92 个当前 OpenAPI 操作一致。

## 10. 最终测试统计

第一轮正式验收：

- 后端：271 passed，2 deselected（仅跳过需手动开启的真实 LLM pytest 标记），0 failed；
- 前端：4 files / 54 tests passed；
- operation catalog：92 operations verified；
- 前端生产构建：通过。

第二轮重复执行同一套命令，结果仍为：后端 271 passed、2 deselected、0 failed；
前端 54 passed；92 个 OpenAPI operation 校验通过；生产构建通过。两轮结果一致。

进入 Iteration 3 前的公共文件 Diff 审查又恢复了统一 ORM 注册和非开发环境零写库
契约，并修复孤儿行动项更新的 fail-open。提交前最终组合验证为：后端 277 passed、
2 deselected、0 failed；前端 54 passed；前端生产构建通过；102 个后端 method/path
及 operationId 全部唯一。

## 11. `.env` 安全状态

- 当前 `.env` 被 `.gitignore` 的 `**/.env` 规则忽略；
- 当前 Git 只跟踪占位配置 `.env.example`，不跟踪 `.env`；
- Git 历史中存在早期 `.env` 提交记录，提交 `a41ebc8` 才停止跟踪，因此不能声称历史从未包含 `.env`；
- 应轮换历史上可能出现过的数据库和 LLM 密钥；本轮对话中明文提供过的 LLM 密钥也应立即撤销并重建。

## 12. 主要修改文件

除已在前序提交纳入的 migration、seed、数据库契约、五轮 E2E 和前端重试文件外，本次收口还修改：

- `services/reporting/assistant/answer_composer.py`
- `services/reporting/assistant/intent_parser.py`
- `services/reporting/assistant/service.py`
- `services/reporting/llm_client.py`
- `tests/conftest.py`
- `tests/test_llm_client.py`
- `tests/test_report_assistant_answer_grounding.py`
- `tests/test_report_assistant_v2_llm_contract.py`
- `frontend/src/components/report-assistant/ReportAssistantPanel.tsx`
- `frontend/src/api/operation-catalog.ts`
- `frontend/src/api/student.ts`
- `routers/report.py`、`routers/daily_report.py`、`routers/__init__.py`、`main.py`、`config.py`

`main.py` 和公共路由注册的修改来自合并覆盖后的恢复，经用户明确选择最小恢复方案 A 后执行；未修改风险规则和 Aggregator 指标口径。

## 13. 剩余限制与建议

- pytest 仍提示 Starlette/httpx、Pydantic V2 迁移和 pytest cache 权限警告，不影响本轮通过结果；
- 数据库报告类型采用 Registry + VARCHAR，状态/触发来源仍采用 ENUM，后续新增枚举值必须配套迁移；
- 历史密钥应完成轮换；
- 当前建议：Iteration 2B.2 可验收，但在密钥轮换完成前不要把环境视为安全收口。完成安全动作后，可以另开任务评审是否进入 Iteration 3；本任务不自动进入。
