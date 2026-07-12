# Iteration 2B 完成报告 — 前端最小对话面板与真实链路验收

**日期**：2026-07-11
**分支**：Berlin
**基线**：257 passed, 2 skipped → **257 passed, 2 skipped（后端零回归）+ 37 passed（前端新增）**

---

## 1. 修改文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/types/report-assistant.ts` | 智能报告助手 TypeScript 类型定义（对齐后端 Pydantic Schema） |
| `frontend/src/api/report-assistant.ts` | API 层封装（POST /reports/assistant/messages） |
| `frontend/src/components/report-assistant/ReportAssistantPanel.tsx` | 对话面板主组件（侧边抽屉 + 状态管理） |
| `frontend/src/components/report-assistant/ReportAssistantMessage.tsx` | 单条消息组件（用户/助手/系统） |
| `frontend/src/components/report-assistant/ReportAssistantEvidence.tsx` | 证据卡片组件（五元绑定展示） |
| `frontend/src/components/report-assistant/ReportAssistantDataQuality.tsx` | 数据质量提示组件 |
| `frontend/src/components/report-assistant/ReportAssistantSuggestions.tsx` | 建议追问按钮组件 |
| `frontend/src/components/report-assistant/ReportAssistantComposer.tsx` | 消息输入区域组件 |
| `frontend/src/components/report-assistant/index.ts` | 组件桶导出 |
| `frontend/src/__tests__/report-assistant-api.test.ts` | API 层测试（8 tests） |
| `frontend/src/__tests__/report-assistant-components.test.tsx` | 组件测试（24 tests） |
| `frontend/src/__tests__/report-assistant-security.test.tsx` | 安全测试（5 tests） |
| `frontend/src/test-setup.ts` | Vitest 测试环境初始化 |

### 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/pages/reports/ReportListPage.tsx` | 修改 | 新增"智能助手"按钮 + 面板集成 |
| `frontend/src/pages/reports/ReportDetailPage.tsx` | 修改 | 新增"智能助手"按钮 + 面板集成（传 current report_id） |
| `frontend/vite.config.ts` | 修改 | 新增 vitest 配置 |
| `frontend/package.json` | 修改 | 新增 vitest/@testing-library 依赖和 test 脚本 |

### 未修改文件（遵守修改边界）

`routers/`、`services/reporting/`、`models/`、`main.py`、`config.py`、所有后端测试、所有其他业务模块。

---

## 2. 智能助手入口位置

```text
报告中心（ReportListPage）
  → 右上角 "智能助手" 按钮（Bot 图标）
  → 打开右侧滑动面板（不离开当前页面）

报告详情（ReportDetailPage）
  → 右上角 "智能助手" 按钮
  → 打开面板并自动传入 current report_id / report_type
```

点击按钮后，右侧滑入 480px 宽面板。关闭面板后原页面状态不丢失。

---

## 3. 对话面板组件结构

```text
ReportAssistantPanel（主组件 — 状态管理 + 抽屉容器）
├── 空状态示例问题（4 个通用问题按钮）
├── ReportAssistantMessage（消息气泡）
│   ├── 用户消息（右对齐，primary 色）
│   ├── 助手消息（左对齐，含状态标记）
│   │   ├── generating → 报告 ID + 时间假设 + 查看详情按钮 + 提示追问
│   │   ├── completed → 回答文本 + 报告跳转链接
│   │   ├── needs_clarification → 澄清问题（普通展示，非错误）
│   │   ├── permission_denied → 权限不足（红色，无证据）
│   │   ├── not_found → 未找到（建议重新生成）
│   │   └── error → 稳定错误提示 + 重试按钮
│   └── 系统消息（居中灰色标签）
├── ReportAssistantDataQuality（数据质量横幅）
│   ├── ok → 默认不展示
│   ├── warning → 黄色"部分数据缺失"
│   ├── empty → 灰色"当前周期无有效数据"
│   ├── degraded → 橙色"报告处于降级状态"
│   └── failed → 红色"不能基于当前报告分析"
├── ReportAssistantEvidence（证据卡片）
│   ├── 默认：label + value + unit
│   ├── 展开："查看依据" → 来源表 / 公式 / 报告 ID
│   └── 安全免责："AI 根据报告数据生成解释，关键数字请以证据卡片和原报告为准。"
├── ReportAssistantSuggestions（追问 Chips）
│   └── 点击后填入文本直接发送
└── ReportAssistantComposer（输入区域）
    ├── Textarea（Enter 发送，Shift+Enter 换行）
    ├── 发送按钮（发送中显示 spinner）
    └── 2000 字符上限
```

---

## 4. API 类型和调用方式

### 类型定义

对齐后端 `services/reporting/assistant/schemas.py`：

| 前端类型 | 后端 Schema |
|---------|------------|
| `ReportAssistantIntent` | `ReportAssistantIntent` (str Enum) |
| `ReportAssistantStatus` | `status: Literal[...]` |
| `ReportAssistantMessageRequest` | `ReportAssistantMessageRequest` |
| `ReportAssistantMessageResponse` | `ReportAssistantMessageResponse` |
| `ReportConversationContext` | `ReportConversationContext` |
| `ReferencedEntity` | `ReferencedEntity` |
| `EvidenceItem` | `EvidenceItem`（五元绑定） |
| `AssistantDataQuality` | 内联 `data_quality: dict` |
| `AssistantMessage` | 前端本地消息状态（非后端 Schema） |

### API 调用

```typescript
// frontend/src/api/report-assistant.ts
export async function sendReportAssistantMessage(
  request: ReportAssistantMessageRequest,
): Promise<ReportAssistantMessageResponse>
```

调用方式：
```text
POST /api/v1/reports/assistant/messages
→ 复用 apiClient（自动 Bearer Token + 统一错误处理）
→ 不在组件中直接写 fetch 或拼接 API URL
```

---

## 5. conversation_context 保存方式

- **仅组件本地状态**（React `useState`）
- 每次收到后端响应 → `response.conversation_context` 覆盖本地 context
- 下一次请求原样传回（不自行重建任何字段）
- 不写入 localStorage、IndexedDB、URL 参数或服务端数据库
- 刷新页面 → 会话丢失（当前阶段可接受限制）
- 从详情页打开时初始化 `last_report_id` 和 `last_report_type`

---

## 6. 各状态展示方式

| 状态 | HTTP | 界面展示 |
|------|------|---------|
| **generating** | 202 | 报告 ID + 报告类型 + 时间假设 + "查看报告详情"按钮 + "报告生成好了吗？"提示 |
| **completed** | 200 | 回答文本 + 证据卡片 + 数据质量 + 建议追问 + 报告跳转链接 |
| **needs_clarification** | 200 | 澄清问题（普通消息气泡，非错误色） + 输入框保持可用 |
| **permission_denied** | 403 | 红色"权限不足" + 不展示 evidence/context metadata/敏感 report type |
| **not_found** | 404 | "报告不存在或已不可访问" + 建议重新生成（不自动生成） |
| **error** | 500 | 稳定错误提示 + 重试按钮（不展示堆栈/异常类名/SQL/API Key/数据库信息） |
| **功能关闭** | 503 | "智能报告助手当前未启用，原报告功能仍可正常使用。"（面板内展示，非 toast） |

---

## 7. DataQuality 展示

独立组件 `ReportAssistantDataQuality`：

| 等级 | 颜色 | 展示 |
|------|------|------|
| ok | 无 | 默认不展示（warnings 为空时不渲染） |
| warning | 黄色 `bg-yellow-50` | "部分数据缺失" + 警告列表 |
| empty | 灰色 `bg-gray-50` | "当前周期无有效数据" |
| degraded | 橙色 `bg-orange-50` | "报告处于降级状态" |
| failed | 红色 `bg-red-50` | "不能基于当前报告分析" |

前端只展示后端结果，不自行改变回答强度。

---

## 8. Evidence 展示

独立组件 `ReportAssistantEvidence`：

**默认展示**：
- label + value + unit（一行）

**展开后（"查看依据"）**：
- entity_id + metric_name
- source_tables
- formula
- source_report_id

**安全要求已实现**：
- ✅ 不展示空公式或空表名占位符
- ✅ 不从前端 AI 文本重新抽取数字生成卡片
- ✅ 不在前端更改 evidence 数值
- ✅ 证据与 AI 文本分开展示
- ✅ 轻量免责说明（"AI 根据报告数据生成解释，关键数字请以证据卡片和原报告为准。"）

---

## 9. 建议追问交互

组件 `ReportAssistantSuggestions`：
- `suggested_follow_ups` 渲染为 `Button variant="outline" size="sm"` Chips
- 点击后直接调用 `handleSend(text)`（等同用户输入）
- 使用当前 `conversation_context`
- 生成新的 `client_request_id`
- 不在前端自行解释追问含义
- 发送中（`isSending`）禁用所有追问按钮

---

## 10. report_id 跳转方式

当响应中存在 `report_id` 时：
- `generating` 状态 → "查看报告详情"按钮 → `<Link to={`/reports/${reportId}`}>`
- `completed` 状态 → "查看完整报告"按钮 → 同上

跳转复用项目现有 React Router 路由 `/reports/:id`（ReportDetailPage），不硬编码路径。

从详情页打开面板时初始化：
```typescript
conversation_context.last_report_id = currentReportId
conversation_context.last_report_type = currentReportType
```

---

## 11. 前端测试结果

```text
Test Files  3 passed (3)
Tests      37 passed (37)
```

### API 测试（8 tests）

| 测试 | 结果 |
|------|------|
| 发送消息时携带 conversation_context | ✅ |
| 重试时保留原 client_request_id | ✅ |
| 处理 HTTP 202 generating 响应 | ✅ |
| 处理 HTTP 403 permission_denied 响应 | ✅ |
| 处理 HTTP 404 not_found 响应 | ✅ |
| 处理 HTTP 500 服务端错误 | ✅ |
| 处理 HTTP 503 服务不可用 | ✅ |
| 返回的 evidence 包含完整五元绑定 | ✅ |

### 组件测试（24 tests）

| 测试 | 结果 |
|------|------|
| 渲染用户消息 | ✅ |
| 渲染助手消息 | ✅ |
| 渲染 generating 状态 | ✅ |
| 渲染澄清为普通消息（非错误） | ✅ |
| 渲染数据质量 warning 提示 | ✅ |
| 渲染证据卡片 | ✅ |
| 渲染建议追问按钮 | ✅ |
| permission_denied 不渲染证据 | ✅ |
| 证据默认展示 label + value + unit | ✅ |
| 点击查看依据后展开来源表和公式 | ✅ |
| 空证据列表不渲染任何内容 | ✅ |
| 不展示空公式占位符 | ✅ |
| ok 状态无警告时不显示 | ✅ |
| warning 状态显示黄色提示 | ✅ |
| empty 状态显示无数据提示 | ✅ |
| degraded 状态显示降级提示 | ✅ |
| failed 状态显示红色提示 | ✅ |
| 点击追问按钮触发回调 | ✅ |
| 发送中禁用追问按钮 | ✅ |
| 空建议列表不渲染 | ✅ |
| 点击发送按钮触发回调 | ✅ |
| Enter 键发送消息 | ✅ |
| 发送中禁用输入和按钮 | ✅ |
| 空消息不允许发送 | ✅ |

### 安全测试（5 tests）

| 测试 | 结果 |
|------|------|
| 不渲染后端堆栈信息 | ✅ |
| 不从 answer 文本重新构建证据 | ✅ |
| 心理证据隐藏敏感字段 | ✅ |
| permission_denied 不渲染证据卡片 | ✅ |
| error 状态不渲染 report_type 敏感信息 | ✅ |

---

## 12. 前端构建结果

```text
vite v8.1.4 building client environment for production...
✓ 2426 modules transformed.
✓ built in 370ms

dist/index.html                          0.87 kB
dist/assets/index-wovYh-LT.css          62.09 kB
dist/assets/vendor-data-C2g0yRPH.js     84.23 kB
dist/assets/vendor-ui-qXsYxuT-.js      101.56 kB
dist/assets/index-Dc4Y-HP9.js          145.51 kB
dist/assets/vendor-misc-aw_UruNt.js    184.40 kB
dist/assets/vendor-react-D3olhxvm.js   270.41 kB
```

TypeScript 类型检查通过，零错误。

---

## 13. 真实 MySQL 四轮验收结果

**未执行。** 原因：当前环境无法启动 MySQL 数据库和完整 FastAPI 后端。

建议验收步骤（需人工执行）：

### 准备条件
1. MySQL 中存在一条已完成的 `application_risk` 报告（至少 2 个风险项目 + metric_traces）
2. 测试用户有 admin 权限
3. `REPORT_ASSISTANT_ENABLED=true`
4. 先用 `REPORT_ASSISTANT_LLM_ENABLED=false` 验证确定性模板

### 预期四轮流程

```text
Turn 1: "看看现在的申请风险"
  → 202 + generating + report_id + 报告类型 + 时间假设

Turn 2: "最严重的是哪几个？"
  → 200 + report_id 不变 + 风险按分数降序 + referenced_entities

Turn 3: "第一个为什么这么高？"
  → 200 + 正确映射第一个 application_id + 风险原因与原报告一致

Turn 4: "这个风险分怎么算？"
  → 200 + source_tables + formula + filters + 统计周期 + 不重新生成报告
```

### 状态
- [ ] 确定性模板四轮验收（REPORT_ASSISTANT_LLM_ENABLED=false）
- [ ] 真实 LLM 四轮验收（REPORT_ASSISTANT_LLM_ENABLED=true）

---

## 14. 真实 LLM Smoke Test 是否执行

**未执行。** 需要有效的 LLM API Key (`REPORT_LLM_API_KEY`) 和 `REPORT_ASSISTANT_LLM_ENABLED=true`。

待验证项：
- [ ] 占位符 {{E1}} 替换正常
- [ ] 没有裸业务数字
- [ ] evidence 卡片值与原报告一致
- [ ] LLM 失败可以降级到确定性模板

---

## 15. 公共文件修改情况

**无公共文件修改。**

`routers/`、`services/`、`models/`、`main.py`、`config.py`、数据库表结构均未改变。

---

## 16. 已知限制

1. **会话不持久化**：刷新页面后对话历史丢失。这符合 Iteration 2B 的设计范围（仅组件本地状态）。

2. **无自动轮询**：generating 状态不自动无限轮询。用户需手动点击"报告生成好了吗？"追问来查询状态。

3. **仅支持应用内路由跳转**：report_id 跳转使用 React Router `<Link>`，仅在 SPA 内有效。

4. **没有 Drawer/Sheet 动画**：面板使用 CSS `fixed` 定位 + 遮罩层。未使用 `@radix-ui/react-dialog` 的原生动画（项目未安装 Sheet 组件）。

5. **不支持 Markdown 渲染**：AI 回答以纯文本展示（`whitespace-pre-wrap`），不支持 Markdown 富文本格式。

6. **未对接实时状态更新**：generating 状态的报告完成后，不通过 WebSocket/SSE 通知前端。

7. **未执行真实 MySQL + LLM 验收**：所有验收通过 Mock 测试和构建验证完成。真实环境验收需人工执行。

8. **evidence 组件只能逐个展开**：一次只能展开一条 evidence 的详情（可扩展为独立展开状态）。

---

## 17. 是否建议进入 Iteration 3

**建议进入 Iteration 3，但前提是先完成 Iteration 2B 的真实 MySQL 四轮人工验收。**

Iteration 2B 已完成：
- ✅ 前端 TypeScript 类型定义（完全对齐后端 Schema）
- ✅ API 层封装（复用 apiClient + 统一错误处理）
- ✅ 6 个对话面板组件（Panel/Message/Evidence/DataQuality/Suggestions/Composer）
- ✅ 报告中心和报告详情双入口
- ✅ 全部 7 种状态展示（generating/completed/clarification/permission_denied/not_found/error/503）
- ✅ 证据五元绑定卡片（展开/收起交互）
- ✅ 数据质量 5 级展示
- ✅ 建议追问 Chips 交互
- ✅ 多轮 conversation_context 自动传回
- ✅ report_id 跳转原报告详情
- ✅ 37 个前端测试全部通过
- ✅ TypeScript 类型检查零错误
- ✅ Vite 生产构建通过
- ✅ 后端 257 测试零回归
- ✅ 不新增数据库表
- ✅ 不修改公共文件
- ✅ 不修改报告业务规则

待完成（人工）：
- [ ] 真实 MySQL 确定性模板四轮验收
- [ ] 真实 LLM Smoke Test

建议待上述验收通过后，再批准进入 Iteration 3（会话持久化、Redis、跨报告比较等）。
