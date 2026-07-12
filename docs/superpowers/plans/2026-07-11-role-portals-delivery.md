# 客服用户端与学生角色门户交付实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有国际教育编辑型门户中补齐学生与咨询用户端的角色隔离、真实业务入口、自动化验证和桌面/移动端验收。

**Architecture:** 保留单一 React 应用和既有后端契约，以 `role_code` 作为登录落点、侧栏导航和路由守卫的统一依据。学生服务继续通过 `/api/v1/client/*` typed API 访问，管理员预览只改变前端呈现，不改变 Token 身份。

**Tech Stack:** React 19、TypeScript、React Router、TanStack Query、Zustand、Axios、Tailwind CSS v4、shadcn/ui、FastAPI、MySQL。

## Global Constraints

- 不修改后端业务接口、请求参数、业务字段和既有路由地址。
- 不新增后端角色，学生与咨询用户体验统一使用 `student`。
- 延续象牙纸白、学院酒红、深墨黑、古铜细线的国际教育编辑型门户语言。
- 不使用虚假 KPI、模拟成绩、模拟签证或模拟申请进度。
- 每次只修改一个页面或一个组件组，并在进入下一组前完成验证。
- 新增或修改的解释性注释使用中文。

---

### Task 1: 角色访问规则与回归验证

**Files:**
- Modify: `frontend/src/lib/role-navigation.ts`
- Modify: `frontend/src/router/index.tsx`
- Modify: `frontend/scripts/verify-editorial-portal.mjs`

**Interfaces:**
- Consumes: `CurrentUser.role_code`、现有路由地址。
- Produces: 默认入口映射、管理/员工/学生允许访问范围的可验证规则。

- [ ] 先扩充门户验证脚本，断言五类角色默认落点、学生受限路由、管理员预览入口和用户管理入口。
- [ ] 运行 `npm test`，确认新增断言能暴露当前缺失的显式访问规则。
- [ ] 以集中配置补齐角色访问规则，并让路由和导航复用同一来源。
- [ ] 再次运行 `npm test`，确认角色规则和 64 个浏览器接口目录均通过。

### Task 2: 学生首页与客服咨询组件组

**Files:**
- Modify: `frontend/src/pages/StudentJourneyPage.tsx`
- Modify: `frontend/src/pages/CustomerServicePage.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: `/client/courses`、`/client/events`、`/client/chat/sessions/*`。
- Produces: 学生首页、会话、课程、活动、报名与取消报名的响应式用户体验。

- [ ] 在结构验证脚本中加入学生能力边界、操作反馈、移动端布局和管理员预览文案断言。
- [ ] 运行验证脚本并记录预期失败项。
- [ ] 统一页面标题、卡片密度、表单间距、按钮状态、空/错/加载状态和窄屏排列。
- [ ] 检查键盘焦点、按钮可访问名称、表单标签和 `prefers-reduced-motion`。
- [ ] 运行 `npm test` 和 TypeScript 构建。

### Task 3: 管理员创建学生账号闭环

**Files:**
- Modify: `frontend/src/api/admin-users.ts`
- Modify: `frontend/src/types/admin.ts`
- Modify: `frontend/src/pages/admin/UserManagementPage.tsx`

**Interfaces:**
- Consumes: `/auth/users`、`/auth/roles`、`/auth/organizations`。
- Produces: 不硬编码密码、可选择现有角色与组织的账号创建表单。

- [ ] 增加组织接口映射的结构断言并运行至失败。
- [ ] 封装组织列表类型和 typed API。
- [ ] 在用户管理表单中增加组织选择、加载、失败和确认反馈。
- [ ] 运行门户结构验证和构建。

### Task 4: 浏览器、规范与工程验收

**Files:**
- Review: `frontend/src/components/layout/*`
- Review: `frontend/src/pages/StudentJourneyPage.tsx`
- Review: `frontend/src/pages/CustomerServicePage.tsx`
- Review: `frontend/src/pages/admin/UserManagementPage.tsx`

**Interfaces:**
- Consumes: 本地 Vite 服务和可用的后端 MySQL 联调环境。
- Produces: 桌面端、390px 移动端截图与可复现的验收记录。

- [ ] 启动本地前端服务并使用 Browser 检查管理员、学生和客服页面。
- [ ] 检查控制台、网络请求、横向溢出、抽屉导航、焦点和确认交互。
- [ ] 获取最新 Web Interface Guidelines，逐文件审查并整改。
- [ ] 运行 `npm run lint`、`npm test`、`npm run build`。
- [ ] 输出修改文件、验证证据、截图位置和真实环境剩余风险。
