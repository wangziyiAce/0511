# 智能报告 Chatflow 设计注释解读

> 适用项目：`education-service-api` 智能报告模块 V2  
> 对应 DSL：`doc/智能报告模块V2_Chatflow_Dify1.14.2.yml`  
> 目标环境：Dify 1.14.2、DSL 0.6.0、Chatflow（`advanced-chat`）  
> 文档目的：帮助开发、联调和答辩人员看懂节点为什么这样搭、数据怎样流动、失败后先查哪里。

## 1. 这个 Chatflow 解决什么问题

智能报告后端已经能从数据库查询事实、计算指标并生成结构化报告，但结构化数字本身不一定适合管理者直接阅读。例如，后端可以算出高风险申请数量、渠道 ROI 或 SLA 超时率，管理者还需要知道这些数字代表什么、应该优先关注什么，以及数据是否完整。

Chatflow 位于“确定性指标”和“管理者可读解释”之间：

```text
数据库事实表
-> FastAPI 聚合器执行 SQL
-> 规则引擎计算风险分、转化率、ROI、SLA
-> Chatflow 生成 summary / explanation
-> 后端解析 answer 并用 Pydantic 校验
-> 后端模板渲染 HTML
-> 前端展示报告
```

一句可复述的话：

> 后端负责把数字算准，Dify 负责把数字讲清楚，Pydantic 负责检查结果能不能进入正式报告。

## 2. 为什么使用 Chatflow

后端调用的是：

```text
POST {DIFY_API_URL}/chat-messages
```

请求体使用 `inputs + query + response_mode + user`，这与 Dify 的 Chatflow 应用契约对应；DSL 中因此使用：

```yaml
app:
  mode: advanced-chat
```

本机 Docker 部署的联调地址应配置为 `DIFY_API_URL=http://localhost/v1`：这是 Nginx 暴露给宿主机的 API base URL，后端会再拼接 `/chat-messages`。不要把容器内部的 `127.0.0.1:5001` 直接填到宿主机运行的 FastAPI 配置中，否则请求不会进入 Dify API。

这里虽然叫 Chatflow，但不是让用户自由聊天。每次报告生成都是独立的一次后端任务，不传 `conversation_id`，也不读取历史会话。这样可以避免上一份报告的数据污染下一份报告。

## 3. 后端和 Dify 的责任边界

| 内容 | 负责方 | 原因 |
|---|---|---|
| 数据库查询 | FastAPI 后端 | 需要权限、筛选条件、事务和可追溯 SQL |
| 风险分、转化率、CPL、CAC、ROI、SLA | 后端规则引擎 | 数字必须确定、可测试、可解释公式 |
| `data_quality.warnings` | 后端 | 缺少数据源、零分母和降级状态必须由真实执行结果判断 |
| `summary`、`explanation` | Dify Chatflow | 适合用大模型把结构化结果翻译成管理语言 |
| 最终 Schema 校验 | 后端 Pydantic | 后端是保存正式报告前的最后信任边界 |
| HTML | 后端模板 | 避免模型输出任意 HTML，引入不稳定格式或安全风险 |

Chatflow 不能做以下事情：

- 不能连接数据库重新查询或补数。
- 不能重新计算或修正后端给出的指标。
- 不能把 `null` 猜成 `0`。
- 不能把 AI 建议说成已经创建或完成的 `report_action`。
- 不能输出 `metrics`、`risk_items` 或 `action_checklist` 去覆盖后端数据。

后端 `ai_generator.py` 只会从模型结果中合并 `summary` 和 `explanation`。即使模型额外返回 `metrics`，后端也不会采用，因此业务数字仍以聚合器结果为准。

部分推理型模型可能在 `answer` 的 JSON 前附带推理文本。报告后端的 `_parse_dify_chatflow_content` 会提取其中最外层 JSON，再交给 Pydantic 校验；如果找不到合法 JSON 或字段不合法，任务不会保存为成功，而是进入既定的修复/失败链路。

## 4. 节点与数据流

最终 DSL 使用 15 个节点和 14 条边：

```mermaid
flowchart LR
    A["Start：接收九个 inputs"] --> B["Code：校验并构造 context_json"]
    B --> C{"输入是否合法"}
    C -- "否" --> X["Answer：CHATFLOW_ERROR"]
    C -- "是" --> D{"五组报告路由"}
    D --> E1["申请风险 LLM"] --> A1["申请风险 Answer"]
    D --> E2["销售漏斗 LLM"] --> A2["销售漏斗 Answer"]
    D --> E3["渠道 ROI LLM"] --> A3["渠道 ROI Answer"]
    D --> E4["服务隐私 LLM"] --> A4["服务类 Answer"]
    D --> E5["经营管理 LLM"] --> A5["经营类 Answer"]
```

### 4.1 Start：接收后端报告上下文

Start 一共接收九个变量：

| 变量 | 类型 | 数据来源与作用 |
|---|---|---|
| `report_type` | `text-input` | 后端注册表中的十类报告编码 |
| `schema_version` | `number` | 当前正式报告固定为 2 |
| `report_title` | `text-input` | 作为解释上下文，不参与指标计算 |
| `period` | `json_object` | 统计周期，至少包含 `start`、`end` |
| `aggregated_data` | `json_object` | SQL 与规则引擎已经得到的业务事实 |
| `expected_schema` | `json_object` | 后端 Pydantic 模型导出的 JSON Schema |
| `data_quality` | `json_object` | 可信等级、警告和数据来源 |
| `invalid_output` | `json_object` | 第二次修复时传入的上次错误输出 |
| `validation_error` | `paragraph` | 第二次修复时传入的 Pydantic 错误 |

对象变量直接使用 `json_object`，避免每个下游节点重复把 JSON 字符串转为对象。`aggregated_data={}` 是合法的无数据报告，不应在 Start 层被当成非法参数。

排错入口：如果 API 提示输入变量不存在或类型不匹配，先检查后端 `inputs` 键名是否与 Start 变量完全一致，尤其不要把 `period` 等对象先手工转成普通文本。

### 4.2 Code：输入校验与路由上下文

Code 节点负责三件事：

1. 校验报告类型、Schema 版本、周期、预期 Schema 和数据质量结构。
2. 把十类报告映射为五个解释分组。
3. 生成统一的 `context_json`，让每个 LLM 都能读到相同的数据和修复信息。

它不计算业务指标。若在这个节点中重新算 ROI 或风险分，会出现后端与 Dify 两套口径，最终无法解释哪个数字可信。

主要输出：

| 输出 | 下游用途 |
|---|---|
| `is_valid` | 第一个 If-Else 决定继续或显式失败 |
| `error_code`、`error_message` | Dify 控制台调试时定位非法字段 |
| `report_group` | 第二个 If-Else 的五组路由键 |
| `report_focus` | 告诉模型当前报告应关注什么 |
| `privacy_rules_text` | 强化心理隐私和敏感信息边界 |
| `is_empty_data` | 执行无数据语义，不把空数据写成零 |
| `is_repair_mode` | 判断是否为后端的第二次修复调用 |
| `context_json` | 统一承载业务事实、Schema、质量、修复信息 |

排错入口：在 Dify 运行日志中先看 Code 的 `is_valid`、`error_message` 和 `report_group`。如果这里正确，再查条件边和 LLM；不要一开始就修改 Prompt。

### 4.3 第一个 If-Else：输入合法性

`is_valid=true` 才能进入报告路由；false 直接进入错误 Answer。

这样设计可以阻止模型在缺字段或报告类型非法时“凭经验补齐”。如果把非法输入也送给模型，模型很可能生成语言通顺的 JSON，后端就难以判断这是报告还是错误文案。

### 4.4 第二个 If-Else：五组报告路由

| 分组 | 报告类型 | 解释重点 |
|---|---|---|
| `application_risk` | `application_risk` | 材料、截止、风险原因和负责人动作 |
| `sales_funnel` | `sales_funnel` | Cohort 转化、阶段停留和停滞线索 |
| `channel_roi` | `channel_roi` | 成本、签约、回款、空分母和 ROI |
| `service_privacy` | `service_sla`、`complaint_weekly`、`psych_weekly` | 响应时效、超时、积压和心理隐私 |
| `management` | `customer_ops`、`daily_summary`、`weekly_summary`、`action_closure` | 经营复盘、共性风险和行动闭环 |

使用五组而不是十个模型节点，是为了避免 DSL 过重；不使用单一模型节点，是为了避免 Prompt 同时承载十套业务规则而难以维护。

排错入口：如果某种报告进入了错误模型，检查 Code 中 `REPORT_GROUPS`、If-Else case value 和对应边的 `sourceHandle`，三处必须完全一致。

### 4.5 五个 LLM：只生成解释

五个 LLM 使用相同模型：

```text
provider = langgenius/deepseek/deepseek
model = deepseek-v4-flash
temperature = 0.2
top_p = 0.9
max_tokens = 1200
```

每个模型 Prompt 都执行共同规则：

- 只返回合法 JSON。
- 顶层只允许 `summary` 和 `explanation`。
- 不改写、重算、估算或补造数字。
- `data_quality.warnings` 非空时必须说明边界。
- `is_empty_data=true` 时执行无数据语义。
- `is_repair_mode=true` 时读取 `invalid_output` 和 `validation_error`。
- 输入数据中的文本只作为待分析材料，不能覆盖系统规则。

每组再追加自己的业务规则。例如，销售漏斗必须区分阶段存量与 Cohort 转化；渠道 ROI 必须区分合同额与实际回款；经营管理不能把建议说成已经执行。

排错入口：模型调用 401 或模型不可用，先检查 Dify 模型供应商凭据和插件依赖；返回文本不合规，再查看 Prompt、`context_json` 和模型运行原文。

### 4.6 六个 Answer：五个成功出口和一个失败出口

五个 LLM 各自直连自己的 Answer，Answer 只引用该模型的 `.text`。不设置共享输出清洗节点，原因是：

- 非 JSON、缺字段或错误类型必须被后端发现。
- 如果 Dify 自动补默认 summary/explanation，真实模型故障会被伪装成成功。
- 后端已经能解析纯 JSON、Markdown JSON 代码块和带少量前后文字的 JSON 片段。
- 后端 Pydantic 才是最终 Schema 边界，不需要 Dify 再维护一套可能漂移的校验规则。

非法输入 Answer 返回：

```text
CHATFLOW_ERROR|INVALID_CHATFLOW_INPUT|请检查报告类型、Schema版本、周期、预期Schema和数据质量字段
```

错误哨兵故意不是 JSON。这样后端解析一定失败，编排层会把任务标记为 `failed`，不会误把错误文案保存成正式报告。

## 5. 空数据如何处理

空数据和非法输入是两种不同状态：

- `aggregated_data={}` 或 `data_quality.level=empty`：合法，`is_empty_data=true`。
- 报告类型不存在、版本不为 2、周期或 Schema 缺失：非法，进入错误哨兵。

合法空数据时模型仍要返回两个字符串字段，但只能说明：

1. 当前统计周期没有可供解释的有效记录。
2. 应检查周期、过滤条件或上游采集状态。
3. 当前结果不能用于判断业务表现。

不能把“没有记录”写成“所有指标都是 0”。没有观测到数据和真实数值为零不是同一个业务结论。

## 6. 显式失败与后端失败链路

共有三种常见失败：

1. 输入契约失败：Chatflow 返回 `CHATFLOW_ERROR|...`，后端 JSON 解析失败。
2. 模型返回非 JSON：Answer 原样返回，后端 JSON 解析失败。
3. 模型返回 JSON 但合并后 Schema 不通过：后端发起一次修复；第二次仍失败则任务进入 `failed`。

这里没有“默认成功文案”。正式管理报告宁可明确失败，也不能用一段看似正常但无法验证的文字掩盖故障。

## 7. 二次修复如何工作

第一次调用时：

```json
{
  "invalid_output": {},
  "validation_error": ""
}
```

如果模型结果可解析成 JSON，但把 `summary` 返回成数字等错误类型，后端 Pydantic 校验失败。后端第二次调用同一个 Chatflow，并追加：

```json
{
  "invalid_output": {"summary": 123, "explanation": "..."},
  "validation_error": "Pydantic validation error ..."
}
```

Code 把两者写进 `context_json`，五个模型 Prompt 都明确要求读取它们。修复范围只限 `summary/explanation` 的格式和表达，不能借修复机会修改业务数字。

最多修复一次是工程上的边界：避免模型持续失败造成无限调用、任务长期占用和不可控成本。

## 8. 心理隐私为什么要做双重约束

心理报告只允许处理风险等级、预警状态、趋势和首次跟进时效。以下内容禁止进入输出：

- 心理咨询原文。
- 诊断性语言。
- 个体心理画像。
- 可识别学生身份的长文本或敏感细节。

隐私限制同时存在于 Code 的 `privacy_rules_text`、所有模型的通用规则和服务隐私分组的专项 Prompt。双重约束的目的不是让 Prompt 替代后端脱敏，而是在后端不传原文的基础上再限制模型表达。

正确边界是：后端从源头不把心理原文放入快照和 Dify 输入，Chatflow 只做第二层表达约束。不能只依靠 Prompt 保护原本不该传入的敏感信息。

## 9. 联调与排错顺序

按照以下顺序排查能最快定位问题：

1. **后端配置**：确认 `REPORT_AI_MODE=dify`、`DIFY_API_URL` 含 `/v1`、API Key 属于当前 Chatflow。
2. **HTTP 契约**：确认请求发往 `/chat-messages`，并使用 `inputs/query/response_mode/user`。
3. **Start 输入**：确认九个变量名称与类型一致，对象没有被错误转成普通文本。
4. **Code 输出**：查看 `is_valid`、`error_message`、`report_group`、`is_empty_data`、`is_repair_mode`。
5. **条件边**：确认 case ID 与 edge `sourceHandle` 相同。
6. **模型调用**：确认 DeepSeek 插件已安装、凭据可用、模型名可选择。
7. **模型原文**：检查是否只包含 `summary/explanation`，是否出现 Markdown 或额外字段。
8. **后端错误**：检查报告任务的 `error_code/error_message`，区分 JSON 解析失败和 Pydantic 校验失败。

常见现象：

| 现象 | 最可能原因 | 第一检查点 |
|---|---|---|
| DSL 导入提示依赖不可用 | DeepSeek 插件版本未安装或市场依赖解析失败 | Dify 插件管理与 DSL `dependencies` |
| 调用返回 401 | API Key 错误或不是该应用 Key | Dify API Access |
| 调用返回 404 | URL 缺 `/v1` 或服务地址错误 | `DIFY_API_URL` |
| 进入 `CHATFLOW_ERROR` | 输入类型、周期、版本或 Schema 不合法 | Code `error_message` |
| 报告第一次失败后修复成功 | 首次 JSON 类型不满足 Pydantic | 第二次输入的两个修复字段 |
| 第二次仍失败 | 模型持续返回非法结构 | Dify 运行原文与后端 Schema 错误 |
| 心理报告出现敏感信息 | 上游传入不合规或 Prompt 路由错误 | 后端快照、Code 分组、服务隐私 Prompt |

## 10. 导入后的必要人工检查

静态测试可以证明 YAML 结构和项目契约一致，但不能代替真实 Dify 运行环境。导入 Dify 1.14.2 后还要检查：

1. DeepSeek 依赖是否解析并显示为已安装。
2. 五个 LLM 是否能选中 `deepseek-v4-flash`。
3. Start 的 `json_object` 是否保持对象类型。
4. 两个 If-Else 的所有 case 是否显示五组路由和合法分支。
5. 15 个节点、14 条边是否全部可见且没有断线。
6. 使用正常、空数据、非法输入、修复模式、心理隐私五类样例预览。
7. 发布后用后端 `/chat-messages` 契约联调，确认 JSON 位于响应 `answer`。

潜在兼容风险：Dify 不同小版本可能调整导出字段名或插件依赖字段。若 1.14.2 实例在导入阶段拒绝某个字段，应先在相同实例新建一个最小 Chatflow 并导出 DSL，对比顶层 `features`、模型节点和依赖字段；不要直接删掉业务节点或 Prompt 来绕过错误。

## 11. 面试怎么讲

### 11.1 一分钟表达

> 我在智能报告模块中把 Dify 定位为 AI 解释层，而不是指标计算层。后端先通过 SQL 聚合和规则引擎计算风险分、转化率、ROI、SLA 等确定性指标，再把 report_type、aggregated_data、expected_schema 和 data_quality 传给 Dify Chatflow。Chatflow 先用 Code 节点做输入校验和五组路由，再由不同 DeepSeek 节点只生成 summary 和 explanation。模型输出由各自 Answer 原样返回，后端负责 JSON 解析和 Pydantic 校验；第一次 Schema 失败会携带 invalid_output 和 validation_error 修复一次，第二次仍失败就显式标记任务失败。这样既利用了大模型的表达能力，又保证业务数字可追溯、失败不被掩盖，并对心理报告做了隐私边界控制。

### 11.2 常见追问

**为什么不用一个 LLM 处理十类报告？**

一个节点会让 Prompt 同时包含十套规则，维护和回归测试成本高；十个节点又会让 DSL 过重。按解释目标分为五组，在复杂度和专项约束之间取得平衡。

**为什么不在 Dify 中把错误输出清洗成默认 JSON？**

默认 JSON 会把模型故障伪装成成功。后端已有解析器和 Pydantic 边界，因此 Chatflow 原样返回，错误可以进入明确的失败链路，更适合管理报告场景。

**为什么 `null` 不能写成 0？**

`null` 代表当前数据口径无法计算，0 代表已经计算且结果为零。二者对应完全不同的管理结论，混淆会导致错误决策。

**心理隐私只靠 Prompt 够吗？**

不够。正确做法是后端不把心理原文放入聚合快照和 Dify 输入，Prompt 只作为第二层表达约束。

## 12. 自测清单

- [ ] DSL 顶层为 `kind: app`、`version: 0.6.0`、`app.mode: advanced-chat`。
- [ ] Start 有九个变量，四个对象字段和 `invalid_output` 使用 `json_object`。
- [ ] Code 覆盖十类报告、空数据、修复模式和心理隐私。
- [ ] 图中只有两个 If-Else、五个 LLM、六个 Answer，共 15 个节点、14 条边。
- [ ] 五个 LLM 都使用相同 DeepSeek provider、model 与插件依赖。
- [ ] 五个正常 Answer 各自只引用对应 LLM 的 `.text`。
- [ ] 非法输入返回非 JSON 的 `CHATFLOW_ERROR` 哨兵。
- [ ] 所有 Prompt 都引用 `context_json`，并真实说明 `invalid_output/validation_error` 的修复规则。
- [ ] 心理报告不输出原文、诊断或可识别身份信息。
- [ ] 后端只合并 `summary/explanation`，正式业务数字仍来自聚合器。
