# Iteration 2B.2 交付收口设计

## 1. 目标

在不进入 Iteration 3、不改变报告业务规则和指标口径的前提下，完成智能报告助手 Iteration 2 的工程化交付收口：数据库迁移版本化、真实同报告五步闭环、测试隔离、MetricTrace 证据编号、前端重试幂等、真实 403/404 以及前后端完整验证。

## 2. 当前基线

- 当前分支为 `Berlin`，工作树包含尚未提交的 Iteration 2B/2B.1 代码和文档。
- 项目没有 Alembic，也没有既有 `migrations/` 目录。
- `.env` 当前被 `.gitignore` 的 `**/.env` 规则排除，未被 Git 跟踪。
- 规定的后端测试范围实际收集 259 项，基线结果为 255 passed、4 failed。
- 4 项失败集中在异步契约和后台任务幂等测试；日志显示真实 LLM 配置泄漏到本应使用确定性配置的后续测试，属于测试状态隔离问题。

## 3. 实施原则

采用当前工作树外科式收口：保留并保护已有未提交改动，只修改任务允许范围内且能直接对应验收要求的文件。所有行为修复遵循测试先行，先复现失败，再做最小实现。不会引入 Alembic、Redis、RAG、跨报告分析、会话持久化或新的业务规则。

## 4. 数据库迁移设计

新增 `migrations/` 目录，并以版本号组织三类 SQL：

1. upgrade SQL：
   - 在修改字段前检查 `report_generation` 中是否存在目标契约之外的旧值。
   - 同步 `report_type` 可接受值与当前 `REPORT_REGISTRY`。
   - 确保 `status` 接受 `pending`、`generating`、`completed`、`failed`。
   - 扩展 `trigger_source` 到能够容纳当前合法值的契约。
2. downgrade SQL：
   - 在缩小字段契约前检查当前数据能否安全回退。
   - 不通过静默截断或默认替换掩盖不兼容数据。
3. seed SQL：
   - 使用 A1024、A1058、A1091 等测试 application_id。
   - 不包含真实个人信息。
   - 可重复执行且提供清理语句。
   - 通过现有确定性规则产生至少两个风险实体。

增加 Schema 契约测试，验证 Registry 报告类型是迁移后数据库允许类型的子集，并验证四个报告状态均在迁移契约中。记录“Registry 可动态扩展而数据库 ENUM 需要迁移”的技术债，但本轮不把字段改成 VARCHAR。

## 5. 后端收口设计

### 5.1 测试隔离

先根据完整套件的失败顺序追踪环境变量、助手设置缓存、LLM Client 和模块级状态。测试必须通过 fixture、monkeypatch 生命周期或明确的缓存清理恢复原状态；不得通过重排、随机重试或只跑单测规避污染。

### 5.2 MetricTrace Evidence ID

`build_structured_evidence()` 将对 MetricTrace 工具结果按稳定输入顺序生成 `E1`、`E2` 等非空唯一 ID。每条证据保留 `metric_name`、`source_report_id`、`source_tables`、`formula`、`filters` 或 `reference`。占位符替换只接受已注册 Evidence ID，未知 ID 继续触发拒绝或确定性降级。

### 5.3 多轮和错误契约

自动化测试固定以下不变量：

- Turn 1 创建的 `report_id=R` 是五步唯一报告 ID。
- Turn 2 必须通过 assistant 的 `query_report_status`，pending/generating/completed 均不创建新报告。
- Turn 3 返回至少两个按风险分降序的 `referenced_entities`。
- Turn 4 的 entity_id 必须等于 Turn 3 position 1，且风险原因来自原报告内容。
- Turn 5 保持同一 entity_id 并返回完整 MetricTrace。
- Turn 2 至 Turn 5 不增加 `report_generation`。
- 不存在报告通过助手状态查询返回 HTTP 404 和 `not_found`。
- 无权限报告、他人报告和心理报告返回 HTTP 403，不返回证据或敏感内容。

## 6. 前端重试设计

每条用户请求消息保存：

- `clientRequestId`：本次业务请求的幂等键。
- `originalRequest`：发送时的 message、conversation_context 快照和 client_request_id。

普通新消息和建议追问始终创建新的 ID。错误重试从对应失败请求读取原始快照，复用原 message、原 context 和原 ID。`isSending` 继续作为并发门闩，连续点击只能产生一个 API 请求。请求快照只保存在 React 内存状态，不写入 localStorage 或 sessionStorage。

## 7. 真实环境验收设计

### 7.1 迁移

在隔离的空测试数据库执行 upgrade，验证应用启动和报告生成；执行 downgrade 验证可回滚；最后再次 upgrade。所有连接信息来自本地环境变量，不写入文档、日志或 Git。

### 7.2 确定性五步链路

加载可清理 seed 后，使用 `REPORT_ASSISTANT_LLM_ENABLED=false` 执行：生成报告、助手查询状态直到完成、风险钻取、解释第一个、指标追溯。记录唯一 report_id、referenced_entities、实体映射、MetricTrace 和验收前后任务数量。

### 7.3 真实权限和不存在资源

创建或重置本地受控 employee 测试账号，密码仅存在本地环境。验证限制报告、行级权限和心理报告的 403；使用不存在 report_id 和伪造 entity 验证 404/安全澄清。

### 7.4 真实 LLM

在本地已有有效配置且不泄露密钥的条件下，对同一份有风险实体的报告执行 drill_down、explain_risk、explain_metric。验证无未替换占位符、无裸核心数字、实体与证据不发生错配、风险原因不新增、DataQuality 限制不被弱化。外部模型不可用时必须验证确定性降级，并把真实 LLM 验收明确标为未通过或受阻，不能用空风险列表替代。

## 8. 验证策略

- 后端：规定测试集合完整运行两次，每次必须 0 failed。
- 前端：运行 `npm test` 和 `npm run build`。
- 数据库：upgrade、downgrade、upgrade，并验证应用启动和报告生成。
- Git 安全：确认 `.env` 被忽略、当前未跟踪，并审计历史中是否曾提交真实内容。
- 完成前逐项对照 Iteration 2B.2 的完成标准，不以局部测试代替完整验收。

## 9. 修改边界

允许修改助手前后端、助手测试、迁移和 seed、必要的 `.env.example`/`.gitignore` 及相关文档。除非迁移契约确有需要，不修改 `models/report.py`。不修改风险规则、Aggregator 指标口径、公共认证、其他业务模块和 `main.py`。

## 10. 回滚

- 代码回滚按本轮文件级变更执行，不覆盖进入本轮前的工作树改动。
- 数据库通过版本化 downgrade SQL 回退，回退前执行数据兼容检查。
- seed 数据通过专用清理 SQL 删除，仅删除使用本轮测试标识创建的数据。

