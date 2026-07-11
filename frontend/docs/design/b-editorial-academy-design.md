# B「国际教育编辑型门户」前端设计说明

## 品牌与体验定位

绮教智服以“全球教育档案室”为核心隐喻：把留学服务中的资料、路径、判断与陪伴，组织成可阅读、可追溯的编辑化体验。页面使用象牙纸白、酒红、深墨与古铜；通过学院建筑、地球仪、地图、书页与档案拼贴建立国际教育的专业感。

| 角色 | 重点体验 | 视觉策略 |
| --- | --- | --- |
| 潜在客户 | 理解服务与匹配路径 | 全球教育地图、院校档案、清晰下一步 |
| 签约学生 | 管理个人申请旅程 | 旅程时间线、材料清单、人工支持入口 |
| 顾问与运营 | 研判、跟进与交付 | 申请者 dossier、服务台账、风险批注 |
| 管理者 | 阅读事实、洞察与行动 | 编辑化报告章节、事实图表、AI 注释分栏 |

## 设计 Token

- 背景：羊皮纸白 `#F7F2EA`；卡片白 `#FFFDF8`；深墨 `#15171C`。
- 品牌：学院酒红 `#7A1F2B`；深酒红 `#4E111B`；古铜 `#B68C5A`；石灰 `#D9D0C2`。
- 字体：标题使用 Noto Serif SC / Songti SC 回退，正文使用 Inter + Noto Sans SC / PingFang SC；数字与引用用 JetBrains Mono。
- 版式：采用 12 栏编辑网格、24px 基础间距；不对称主视觉与细线分隔并存。圆角仅用于输入、标签与小型资料卡，不把整页做成后台卡片墙。
- 图标与动效：Lucide 线性图标；150–220ms 的章节展开、资料切换和状态过渡；支持 `prefers-reduced-motion`。

## 信息与数据原则

- 业务事实、AI 摘要、管理建议、数据质量说明固定分区；AI 内容标明“AI 生成”，政策回答必须提供来源和免责声明。
- `REAL`、`MOCK`、`PENDING`、`NOT_TESTED` 使用文字、图标与色彩共同表达；不得将 Mock 写成真实联调。
- Loading 使用档案页骨架，Empty 提示缺少资料及下一步，Error 提供重试，权限不足使用页面级说明。写操作显示对象、原/新状态、影响和确认。
- 前端只展示和格式化后端事实；不计算风险、ROI、SLA 或转化指标。

## 页面与示意图索引

| 文件 | 路由 | 主要版式 | 关键状态 |
| --- | --- | --- | --- |
| `01-login.png` | `/login` | 学院封面与登录档案卡 | 校验、Loading、401 |
| `02-dashboard.png` | `/dashboard` | 全球教育服务地图与今日档案 | 数据来源、待办、快捷入口 |
| `03-customer-assessment.png` | `/customer-assessment` | 申请者 dossier 与院校匹配拼贴 | 上传解析、缺失追问、风险 |
| `04-customer-service.png` | `/customer-service` | 对话正文与知识来源索引 | 引用、免责声明、重试 |
| `05-student-assistant.png` | `/student-assistant` | 个人留学旅程与服务清单 | 隐私、求助、人工介入 |
| `06-enterprise-assistant.png` | `/enterprise-assistant` | 顾问服务台账与审批边栏 | 只读、权限、二次确认 |
| `07-report-list.png` | `/reports` | 报告书架与目录筛选 | 分页、空列表、数据质量 |
| `08-report-generate.png` | `/reports/generate` | 报告委托单与资料选择器 | 校验、202 任务、轮询 |
| `09-report-detail.png` | `/reports/:id` | 杂志章节、事实图表与 AI 边注 | schema、来源、失败重试 |
| `10-report-schedules.png` | `/reports/schedules` | 发布日历与计划卡片 | 启停、校验、确认 |
| `11-report-actions.png` | `/reports/actions` | 行动编排板与责任时间线 | 状态流转、影响确认 |
| `12-report-data-maintenance.png` | `/reports/data-maintenance` | 数据档案、来源与质量批注 | 权限、质量预警、修正确认 |

## 响应式与工程边界

桌面端保留编辑网格与资料侧栏；1280px 缩减拼贴密度；1024px 将侧栏变为可展开资料抽屉；768px 以下改为单列章节流，表格横向滚动或卡片化，聊天输入区保持可见。继续复用现有 React、TypeScript、React Query、Zustand 和统一 API Client；本设计资产阶段不改接口、类型或后端业务计算。

## 设计验收

- 12 张 `1440×960` PNG 与本表、同目录 README 一一对应。
- 全部页面使用象牙白/酒红/深墨/古铜体系，并避免彩虹渐变、玻璃拟态和通用后台卡片墙。
- 视觉元素为通用学院建筑、书籍、地图、地球仪、旅行和档案；不使用真实学校、企业或个人标识。
