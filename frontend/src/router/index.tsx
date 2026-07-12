/** 前端路由：保留既有 URL，并将原占位入口替换为真实业务页面。 */
import { createBrowserRouter } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'
import ManagementRoute from './ManagementRoute'
import RoleRoute from './RoleRoute'
import RoleLanding from './RoleLanding'
import AppShell from '@/components/layout/AppShell'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import CustomerAssessmentPage from '@/pages/CustomerAssessmentPage'
import CustomerServicePage from '@/pages/CustomerServicePage'
import StudentJourneyPage from '@/pages/StudentJourneyPage'
import EnterpriseWorkbenchPage from '@/pages/EnterpriseWorkbenchPage'
import ApiWorkbenchPage from '@/pages/ApiWorkbenchPage'
import ReportListPage from '@/pages/reports/ReportListPage'
import ReportGeneratePage from '@/pages/reports/ReportGeneratePage'
import ReportDetailPage from '@/pages/reports/ReportDetailPage'
import ReportActionsPage from '@/pages/reports/ReportActionsPage'
import ReportSchedulesPage from '@/pages/reports/ReportSchedulesPage'
import ReportDataPage from '@/pages/reports/ReportDataPage'
import NotFoundPage from '@/pages/NotFoundPage'
import UserManagementPage from '@/pages/admin/UserManagementPage'
import { managementRoles, staffRoles } from '@/lib/role-navigation'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <ProtectedRoute><AppShell /></ProtectedRoute>,
    children: [
      { index: true, element: <RoleLanding /> },
      { path: 'dashboard', element: <RoleRoute allow={managementRoles}><DashboardPage /></RoleRoute> },
      { path: 'customer-assessment', element: <RoleRoute allow={staffRoles}><CustomerAssessmentPage /></RoleRoute> },
      { path: 'customer-service', element: <CustomerServicePage /> },
      { path: 'student-assistant', element: <StudentJourneyPage /> },
      { path: 'enterprise-assistant', element: <RoleRoute allow={staffRoles}><EnterpriseWorkbenchPage /></RoleRoute> },
      { path: 'enterprise-assistant-placeholder', element: <RoleRoute allow={staffRoles}><EnterpriseWorkbenchPage /></RoleRoute> },
      { path: 'reports', element: <RoleRoute allow={managementRoles}><ReportListPage /></RoleRoute> },
      { path: 'reports/generate', element: <RoleRoute allow={managementRoles}><ReportGeneratePage /></RoleRoute> },
      { path: 'reports/actions', element: <RoleRoute allow={managementRoles}><ReportActionsPage /></RoleRoute> },
      { path: 'reports/schedules', element: <ManagementRoute><ReportSchedulesPage /></ManagementRoute> },
      { path: 'reports/data', element: <ManagementRoute><ReportDataPage /></ManagementRoute> },
      { path: 'reports/:id', element: <RoleRoute allow={managementRoles}><ReportDetailPage /></RoleRoute> },
      { path: 'admin/users', element: <ManagementRoute><UserManagementPage /></ManagementRoute> },
      // 兼容原联调地址；管理员主导航使用更清晰的诊断别名。
      { path: 'workbench/:group', element: <ManagementRoute><ApiWorkbenchPage /></ManagementRoute> },
      { path: 'admin/api-diagnostics', element: <ManagementRoute><ApiWorkbenchPage /></ManagementRoute> },
      { path: '403', element: <NotFoundPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
