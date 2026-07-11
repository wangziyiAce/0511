# education-service-api 项目 Agent 协作规则

本文件是本项目的根级协作规则，适用于所有 Agent、AI 编码助手和协作者。项目是一个教学型、就业导向型的教育服务系统：后端使用 FastAPI、SQLAlchemy、Pydantic 和 MySQL；前端位于 `frontend/`，使用 React + TypeScript；当前已实现认证、智能报告、报告调度、CRM 与学生服务联动，并通过 Dify 生成 AI 内容。

目标不仅是让功能可运行，还要让代码可读、可测试、可排错，并能用于项目复盘和面试表达。变量、函数、类和字段使用英文；模块说明、docstring 和关键注释使用清晰中文。

## 1. 项目结构与模块边界

```text
main.py                    FastAPI 应用入口、生命周期、路由注册
config.py                  环境配置与应用配置
models/                    SQLAlchemy ORM 模型
schemas/                   Pydantic 请求/响应模型
routers/                   HTTP 接口、依赖注入、权限入口
services/                  业务规则与跨模块编排
services/reporting/        报告 V2：注册、聚合、生成、渲染、任务编排
utils/                     数据库、认证、Dify 客户端、通用异常
tests/                     自动化测试
templates/reports/         报告 HTML 模板
frontend/                  React 前端
doc/                       需求、架构、接口和 Dify 契约文档
db_init.sql                MySQL 初始化/迁移参考脚本
report_scheduler.py        独立报告调度进程入口
```

一个功能优先在自己的纵向模块内闭环。例如新增报告能力，通常只修改对应的 `routers/`、`schemas/`、`models/`、`services/reporting/`、`templates/reports/` 与 `tests/`；不要为了方便把业务规则塞进 `main.py`、路由层或通用工具层。

`routers/` 只负责 HTTP 参数、依赖注入、权限入口和响应；`services/` 负责业务规则、事务和外部调用；`models/` 描述持久化结构；`schemas/` 描述接口契约。可复述的结论是：Service 层负责业务规则，Router 层只负责接收请求和返回响应。

## 2. 允许修改范围

开始修改前，先读取与当前任务直接相关的路由、Schema、Service、Model、测试和 `doc/` 中对应设计文档；不要凭名称猜测接口或字段。

默认只修改完成当前功能所需的最小范围：

- 后端业务功能：对应的 `routers/`、`schemas/`、`services/`、`models/`、`tests/`、`templates/reports/` 和必要的接口文档。
- 报告 V2：优先在 `services/reporting/` 内扩展；保持 `services/report_service.py` 仅作为旧导入路径的兼容入口，不在其中堆放新逻辑。
- 前端功能：只修改 `frontend/src/` 中对应页面、组件、API、类型与样式；后端接口改动必须同步核对 `frontend/src/api/`、`frontend/src/types/` 和相关页面。
- 数据库结构：同时修改 ORM Model、`db_init.sql`（或明确迁移方案）、Schema/Service，以及相应测试或验证脚本。
- 文档、DSL、模板：只修改当前需求涉及的 `doc/`、Dify YAML 或 `templates/reports/`，并说明其与后端契约的关系。

不要修改其他成员负责的业务模块、无关文档或无关格式。发现工作区已有改动时，默认视为用户或其他协作者的工作；除非任务明确要求，否则不覆盖、回退、暂存或重排这些改动。

## 3. 受保护的公共文件

以下文件或目录承担全局职责。未经用户明确同意，不得直接修改：

- `main.py`：应用创建、生命周期与全局路由注册。
- `config.py`、`.env`、`.env.example`：运行环境、密钥与连接配置。
- `utils/database.py`：Engine、Session、Base、建表与最小种子数据。
- `utils/auth.py`、`utils/dify_client.py`、`utils/errors.py`：认证、外部 AI 客户端与通用异常契约。
- `requirements.txt`：全项目依赖。
- `db_init.sql`：跨环境数据库初始化基线。
- `report_scheduler.py`：独立调度进程入口。
- `frontend/package.json`、`frontend/package-lock.json`、`frontend/vite.config.ts`、`frontend/tsconfig*.json`：前端构建与依赖基线。
- `frontend/src/lib/`、`frontend/src/components/ui/`：前端共享基础设施与通用 UI 组件。

如确实必须修改受保护文件，先停止直接编辑，并在回复中说明：

1. 为什么无法在现有模块接口内完成；
2. 需要改动哪些受保护文件；
3. 最小改动方案、对已有接口/数据的影响和回滚方式；
4. 等待用户明确确认后再执行。

用户明确授权修改后，仍应只做获授权的最小改动，并同步更新受影响的测试或文档。

## 4. 代码与接口变更原则

- 不为实现当前功能重写公共架构，不删除不理解的既有代码。
- 不硬编码数据库地址、密码、JWT 密钥、Dify API Key 或其他敏感信息；环境差异通过 `.env` 和 `config.py` 解决。
- 不在 Router 中直接拼复杂 SQL、调用 Dify 或实现核心业务流程；这些逻辑归入 Service。
- 需要写库时，明确事务边界：成功 `commit()` 后按需 `refresh()`；异常时 `rollback()`，不要吞掉数据库异常。
- 部分更新使用 `model_dump(exclude_unset=True)`，避免前端未传字段被默认值覆盖。
- 对资源详情、更新、删除、报告和行动项操作，必须考虑认证、角色权限与记录级数据权限；不能只依赖前端隐藏按钮。
- 新接口遵守现有 `/api/v1/` 前缀、Pydantic 响应模型和 HTTP 状态码习惯。异步报告创建保持 `202 + task/report id`，不要同步等待 Dify 完成。
- Dify 调用、报告模板与前端渲染必须遵守已有字段契约；字段、报告类型或 Schema 版本变化时，同步检查 Dify YAML、`services/reporting/registry.py`、响应 Schema、前端 TypeScript 类型和相关测试。
- 定时任务必须考虑幂等、重复执行、失败重试和可观察性，不能因为调度器重复触发而生成不可追踪的重复报告。

## 5. AI 报告与数据链路约束

本项目当前的 AI 重点是智能报告。涉及 AI 或后续 RAG 能力时，注释和设计必须表明所在链路：

```text
用户/调度器请求
-> FastAPI 路由
-> 权限与参数校验
-> 创建报告任务/读取业务数据
-> 聚合与规则计算
-> Dify 或大模型调用
-> 结构化结果校验
-> 报告持久化与 HTML/前端渲染
-> 返回任务状态、结果或错误信息
-> 日志、异常、重试、缓存与权限审计
```

- `services/reporting/registry.py` 是报告类型、权限、Schema 版本和模板映射的单一入口；新增报告类型先扩展注册定义，再补齐聚合、生成、渲染、接口和测试。
- 业务事实数据与 AI 生成文本分开处理。先用 SQL/规则层得到可追溯指标，再把必要上下文传给 Dify；不要让模型替代数据库统计或权限判断。
- 外部 AI 失败时，保留任务状态、错误信息和重试入口；不得把调用失败伪装成成功结果。
- 后续接入文件、OCR、Embedding、Milvus、MinIO、Redis 或 RAG 时，必须明确输入来源、存储位置、向量/缓存键、权限隔离、失败排查入口和成本/性能边界。

## 6. 注释与教学质量

新增或重点修改的 Python/TypeScript 文件应有模块说明，说明职责、所在层级、上游调用者、下游依赖和关键入口。新增或修改的路由、业务函数、Schema、Model、任务函数和测试应写中文 docstring 或等价注释。

注释按以下顺序表达：先说解决什么问题；再说数据从哪里来、如何处理、输出给谁；最后说明异常、权限、边界和排查入口。重点解释“为什么这样写”，不要逐行翻译代码。

以下位置必须有具体中文解释：

- `Depends(get_db)`、`Depends(get_current_user)` 等依赖注入，说明 Session/当前用户来自何处、为什么需要它。
- `commit()`、`refresh()`、`rollback()`、`model_dump(exclude_unset=True)`、`setattr()` 等事务或部分更新关键调用，说明不这样做会有什么风险。
- 权限、状态、分页、筛选、逻辑删除、重试、批处理、异常降级和外部服务调用。
- AI 请求 payload、Dify 响应、聚合指标、报告状态、任务 ID、错误信息等关键中间数据。

避免“创建对象”“调用函数”“返回结果”这类无信息量注释。测试注释至少说明测试目标、准备数据、执行动作和断言为什么能证明业务规则。

## 7. Superpowers 工作流

框架搭建、新模块、CRUD、接口开发、业务逻辑、排错与重构，进入代码修改前必须按任务类型使用相应 Superpowers skill：

- 新功能、新模块、架构调整：先用 `superpowers:brainstorming` 明确目标与设计，再用 `superpowers:writing-plans` 写可执行计划。
- CRUD、接口和业务代码：使用 `superpowers:test-driven-development`，先定义行为和验证方式，再写实现。
- 报错、接口异常、测试失败、数据不符合预期：使用 `superpowers:systematic-debugging`，先定位现象和根因，再修改代码。
- 执行已有计划：使用 `superpowers:executing-plans` 或 `superpowers:subagent-driven-development`，逐步实现和验证。
- 宣称完成前：使用 `superpowers:verification-before-completion`，以实际命令、测试输出或 diff 证明结果。

如果用户要求跳过流程，先简要说明风险；除非用户坚持，不要绕过。

## 8. 完成前自查

- 已阅读相关现有代码、接口和文档，改动位于允许范围内。
- 未改动受保护文件；如已获授权修改，已说明影响和最小方案。
- 后端接口、Schema、Service、Model、数据库脚本、前端类型/Dify 契约之间没有字段漂移。
- 关键权限、事务、异常、幂等、分页或异步任务边界已处理。
- 新增或修改代码具备清晰中文模块说明、docstring 和关键逻辑注释。
- 运行了匹配本次改动的测试、静态检查、构建或最小手工验证，并如实报告结果。
- 运行 `git diff` 与 `git status --short`，确认没有误改任务范围之外的文件；不要处理已有的无关改动。
