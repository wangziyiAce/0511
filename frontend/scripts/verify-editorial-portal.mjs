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
for (const rule of ["student: '/student-assistant'", "employee: '/enterprise-assistant'", "team_leader: '/enterprise-assistant'"]) {
  if (!roles.includes(rule)) throw new Error(`missing role landing rule: ${rule}`)
}

const login = await readFile(new URL('src/pages/LoginPage.tsx', root), 'utf8')
if (!login.includes('getDefaultRoute')) throw new Error('login must redirect by role')

const authStore = await readFile(new URL('src/stores/auth-store.ts', root), 'utf8')
if (!authStore.includes('const currentUser = await getMeApi()')) throw new Error('login must refresh /auth/me before role redirect')

const sidebar = await readFile(new URL('src/components/layout/Sidebar.tsx', root), 'utf8')
if (!sidebar.includes("to: '/admin/api-diagnostics'")) throw new Error('API diagnostics must be admin-only navigation')

console.log('editorial portal structure verified')
