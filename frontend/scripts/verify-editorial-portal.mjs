import { access, readFile } from 'node:fs/promises'

const root = new URL('../', import.meta.url)
const requiredPages = [
  'src/pages/CustomerAssessmentPage.tsx',
  'src/pages/CustomerServicePage.tsx',
  'src/pages/StudentJourneyPage.tsx',
  'src/pages/reports/ReportDataPage.tsx',
  'src/pages/admin/UserManagementPage.tsx',
]
const requiredComponents = [
  'src/components/editorial/EditorialPageHeader.tsx',
  'src/components/editorial/ArchiveCard.tsx',
  'src/components/editorial/StatusStamp.tsx',
  'src/components/editorial/Timeline.tsx',
]

for (const file of [...requiredPages, ...requiredComponents]) {
  await access(new URL(file, root))
}

const css = await readFile(new URL('src/index.css', root), 'utf8')
for (const token of ['--paper:', '--wine:', '--ink:', '--bronze:', 'prefers-reduced-motion']) {
  if (!css.includes(token)) throw new Error(`missing editorial design token or behavior: ${token}`)
}

const router = await readFile(new URL('src/router/index.tsx', root), 'utf8')
for (const page of ['CustomerAssessmentPage', 'CustomerServicePage', 'StudentJourneyPage', 'ReportDataPage']) {
  if (!router.includes(page)) throw new Error(`missing business route: ${page}`)
}

for (const marker of ['RoleRoute', 'UserManagementPage', "path: 'admin/users'"]) {
  if (!router.includes(marker)) throw new Error(`missing role portal route behavior: ${marker}`)
}

const roles = await readFile(new URL('src/lib/role-navigation.ts', root), 'utf8')
for (const rule of [
  "admin: '/dashboard'",
  "manager: '/dashboard'",
  "employee: '/enterprise-assistant'",
  "team_leader: '/enterprise-assistant'",
  "student: '/student-assistant'",
]) {
  if (!roles.includes(rule)) throw new Error(`missing role landing rule: ${rule}`)
}
for (const marker of ['studentPortalRoutes', 'staffPortalRoutes', 'managementPortalRoutes', 'canAccessPortalRoute', 'normalizeRoleCode']) {
  if (!roles.includes(marker)) throw new Error(`missing explicit portal access rule: ${marker}`)
}
for (const restrictedPath of ["'/reports'", "'/enterprise-assistant'", "'/admin/api-diagnostics'"]) {
  if (!roles.includes(restrictedPath)) throw new Error(`missing protected portal path: ${restrictedPath}`)
}

const login = await readFile(new URL('src/pages/LoginPage.tsx', root), 'utf8')
if (!login.includes('getDefaultRoute')) throw new Error('login must redirect by role')

const authStore = await readFile(new URL('src/stores/auth-store.ts', root), 'utf8')
if (!authStore.includes('const currentUser = await getMeApi()')) throw new Error('login must refresh /auth/me before role redirect')
if (!authStore.includes('normalizeRoleCode')) throw new Error('auth store must normalize legacy user_type when role_code is absent')

const sidebar = await readFile(new URL('src/components/layout/Sidebar.tsx', root), 'utf8')
if (!sidebar.includes("to: '/admin/api-diagnostics'")) throw new Error('API diagnostics must be admin-only navigation')
for (const marker of ['focus-visible:ring-2', 'overscroll-contain', 'safe-area-inset']) {
  if (!sidebar.includes(marker)) throw new Error(`missing accessible drawer behavior: ${marker}`)
}

const appShell = await readFile(new URL('src/components/layout/AppShell.tsx', root), 'utf8')
if (!appShell.includes('关闭导航遮罩')) throw new Error('drawer backdrop needs a distinct accessible name')

const studentPortal = await readFile(new URL('src/pages/StudentJourneyPage.tsx', root), 'utf8')
for (const marker of ['真实数据边界', '接口未开放', 'min-w-0']) {
  if (!studentPortal.includes(marker)) throw new Error(`missing student portal UX boundary: ${marker}`)
}

const customerService = await readFile(new URL('src/pages/CustomerServicePage.tsx', root), 'utf8')
for (const marker of ['aria-busy', '暂无匹配课程', '暂无近期活动', 'sm:flex-row', 'Intl.DateTimeFormat', 'break-words']) {
  if (!customerService.includes(marker)) throw new Error(`missing customer service responsive state: ${marker}`)
}

const adminUsersApi = await readFile(new URL('src/api/admin-users.ts', root), 'utf8')
for (const marker of ['getOrganizations', "'/auth/organizations'"]) {
  if (!adminUsersApi.includes(marker)) throw new Error(`missing organization API integration: ${marker}`)
}

const userManagement = await readFile(new URL('src/pages/admin/UserManagementPage.tsx', root), 'utf8')
for (const marker of ['getOrganizations', "['admin', 'organizations']", '选择现有组织']) {
  if (!userManagement.includes(marker)) throw new Error(`missing organization selector behavior: ${marker}`)
}
if (!userManagement.includes('scope="col"')) throw new Error('user table headers need column scope')

console.log('editorial portal structure verified')
