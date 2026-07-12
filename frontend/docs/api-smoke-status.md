# 首版接口联调记录

> 执行日期：2026-07-11；目标地址：`http://127.0.0.1:8001`；登录态：本地开发种子管理员。
>
> 本记录只标记实际执行过的结果。`NOT_TESTED` 不代表成功，也不应用 Mock 结果替代。

## REAL

- `GET /health`：200。
- `POST /api/v1/auth/login`：200；返回统一信封，Token 位于 `data.access_token`。
- `GET /api/v1/auth/me`：200。
- 认证与组织只读：`organizations`、`organizations/tree`、`roles`、`users`：均为 200。
- CRM 线索：`GET /crm/leads`：200。
- 客户研判：`GET /profile/sources`、`GET /profile/rules`：均为 200。
- 安全代理：`GET /client/courses`、`GET /client/events`：均为 200，浏览器请求不携带 Dify Service Token。
- 报告：`GET /reports`、`GET /reports/types`、`GET /report-schedules`：均为 200。
- 报告数据：四类列表（申请材料、渠道成本、合同、回款）均为 200。
- 日报汇总：提供 `report_date=2026-07-11` 后为 200。
- 企业工作台写入闭环：development 数据库中以 `mock_` 前缀创建临时员工、线索、状态流转、跟进和日报；对应写入分别返回 201/200，日报列表与当日汇总均返回 200。

## FAILED

- `GET /api/v1/employee/daily-reports`：500。
  - 根因已通过进程内 TestClient 复现：现有模拟数据把 `key_progress`、`risks` 写成对象；接口 Schema 要求 `list[str]`，序列化时 Pydantic 抛出校验异常。
  - 这不是前端请求或认证失败。工作台保留服务端错误原文，未用前端兜底伪装为空列表。

## NOT_TESTED

- 所有会写入、更新或删除真实数据的接口：未执行成功写入验证，避免在未明确隔离的数据库中产生测试业务数据。
- 需要具体资源 ID 的详情、更新、重试、报名、会话消息、行动和工单接口：未验证成功路径；需要先准备可回收的测试资源和对应角色权限。
- 资料上传的真实文件流：前端已实现文本 `multipart/form-data` 编码，但没有上传真实文件，以避免污染当前数据源。

## 覆盖规则

前端 `scripts/verify-operation-catalog.mjs` 会从后端 OpenAPI 读取客户端可调用操作，并与工作台目录比对。当前校验为 64 个操作；服务端专用 Dify 与旧直连路径不计入浏览器调用范围。
