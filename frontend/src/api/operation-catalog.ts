/**
 * 全接口联调目录。
 *
 * 本文件把后端已注册路由转成前端可发现的操作元数据：页面选择操作后，
 * 由通用工作台统一收集路径参数、查询参数和 JSON 请求体，再交给 API Client。
 * Dify 专用操作明确标记为 serverOnly，浏览器不会携带 Service Token 直连。
 */

export type ApiGroup = 'auth' | 'crm' | 'profile' | 'chat' | 'student' | 'reports' | 'reportData'
export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface ApiOperation {
  operationId: string
  group: ApiGroup
  label: string
  method: ApiMethod
  path: string
  description: string
  /** 查询参数初始值，用于让带必填 Query 的只读接口可直接联调。 */
  defaultQuery?: Record<string, string>
  defaultBody?: Record<string, unknown>
  /** 请求体编码方式；上传资料需要转换为 multipart/form-data，避免后端收不到 Form 字段。 */
  requestKind?: 'json' | 'multipart'
  requiresConfirmation?: boolean
  serverOnly?: boolean
}

const operation = (value: ApiOperation): ApiOperation => value

export const apiOperations: ApiOperation[] = [
  operation({ operationId: 'health', group: 'auth', label: '服务健康检查', method: 'GET', path: '/health', description: '验证后端服务是否启动。' }),
  operation({ operationId: 'login', group: 'auth', label: '用户登录', method: 'POST', path: '/auth/login', description: '获取登录 Token。', defaultBody: { username: '', password: '' } }),
  operation({ operationId: 'me', group: 'auth', label: '当前用户', method: 'GET', path: '/auth/me', description: '读取当前登录用户。' }),
  operation({ operationId: 'users-list', group: 'auth', label: '用户列表', method: 'GET', path: '/auth/users', description: '管理员查询用户。' }),
  operation({ operationId: 'users-create', group: 'auth', label: '创建用户', method: 'POST', path: '/auth/users', description: '管理员创建用户。', defaultBody: { username: '', password: '', role_code: 'employee' }, requiresConfirmation: true }),
  operation({ operationId: 'users-detail', group: 'auth', label: '用户详情', method: 'GET', path: '/auth/users/{user_id}', description: '查询用户详情。' }),
  operation({ operationId: 'users-update', group: 'auth', label: '更新用户', method: 'PUT', path: '/auth/users/{user_id}', description: '更新用户资料。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'users-password', group: 'auth', label: '修改密码', method: 'PUT', path: '/auth/users/{user_id}/password', description: '修改用户密码。', defaultBody: { old_password: '', new_password: '' }, requiresConfirmation: true }),
  operation({ operationId: 'roles-list', group: 'auth', label: '角色列表', method: 'GET', path: '/auth/roles', description: '读取角色配置。' }),
  operation({ operationId: 'organizations-list', group: 'auth', label: '组织列表', method: 'GET', path: '/auth/organizations', description: '读取扁平组织。' }),
  operation({ operationId: 'organizations-tree', group: 'auth', label: '组织树', method: 'GET', path: '/auth/organizations/tree', description: '读取组织层级。' }),
  operation({ operationId: 'organizations-create', group: 'auth', label: '创建组织', method: 'POST', path: '/auth/organizations', description: '创建组织节点。', defaultBody: { org_name: '' }, requiresConfirmation: true }),
  operation({ operationId: 'leads-create', group: 'crm', label: '创建线索', method: 'POST', path: '/crm/leads', description: '录入意向客户。', defaultBody: { customer_name: '', owner_employee_id: 0 }, requiresConfirmation: true }),
  operation({ operationId: 'leads-list', group: 'crm', label: '线索列表', method: 'GET', path: '/crm/leads', description: '分页查询线索。' }),
  operation({ operationId: 'leads-detail', group: 'crm', label: '线索详情', method: 'GET', path: '/crm/leads/{lead_id}', description: '查看单条线索。' }),
  operation({ operationId: 'leads-update', group: 'crm', label: '更新线索', method: 'PUT', path: '/crm/leads/{lead_id}', description: '局部更新线索。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'leads-status', group: 'crm', label: '更新线索状态', method: 'PUT', path: '/crm/leads/{lead_id}/status', description: '推进线索状态。', defaultBody: { status: 'contacting' }, requiresConfirmation: true }),
  operation({ operationId: 'followups-create', group: 'crm', label: '新增跟进', method: 'POST', path: '/crm/leads/{lead_id}/follow-ups', description: '记录跟进。', defaultBody: { employee_id: 0, follow_type: 'phone', content: '' }, requiresConfirmation: true }),
  operation({ operationId: 'followups-list', group: 'crm', label: '跟进列表', method: 'GET', path: '/crm/leads/{lead_id}/follow-ups', description: '读取线索跟进记录。' }),
  operation({ operationId: 'daily-create', group: 'crm', label: '提交日报', method: 'POST', path: '/employee/daily-reports', description: '创建员工日报。', defaultBody: { employee_id: 0, report_date: '', content: '' }, requiresConfirmation: true }),
  operation({ operationId: 'daily-list', group: 'crm', label: '日报列表', method: 'GET', path: '/employee/daily-reports', description: '查询日报。' }),
  operation({ operationId: 'daily-summary', group: 'crm', label: '日报汇总', method: 'GET', path: '/employee/daily-reports/summary', description: '查询指定日期的日报汇总。', defaultQuery: { report_date: new Date().toISOString().slice(0, 10) } }),
  operation({ operationId: 'daily-detail', group: 'crm', label: '日报详情', method: 'GET', path: '/employee/daily-reports/{report_id}', description: '读取单条日报。' }),
  operation({ operationId: 'profile-upload', group: 'profile', label: '上传客户资料', method: 'POST', path: '/profile/upload', description: '首版使用文本资料联调；请求会转换为表单数据。', defaultBody: { source_type: 'text', content_text: '' }, requestKind: 'multipart', requiresConfirmation: true }),
  operation({ operationId: 'profile-sources', group: 'profile', label: '客户来源列表', method: 'GET', path: '/profile/sources', description: '查询解析来源。' }),
  operation({ operationId: 'profile-rules-list', group: 'profile', label: '画像规则列表', method: 'GET', path: '/profile/rules', description: '查询研判规则。' }),
  operation({ operationId: 'profile-rules-create', group: 'profile', label: '创建画像规则', method: 'POST', path: '/profile/rules', description: '创建规则。', defaultBody: { product_line: '', rule_name: '', rule_content: {} }, requiresConfirmation: true }),
  operation({ operationId: 'profile-rules-update', group: 'profile', label: '更新画像规则', method: 'PUT', path: '/profile/rules/{rule_id}', description: '更新规则。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'profile-detail', group: 'profile', label: '研判详情', method: 'GET', path: '/profile/{source_id}', description: '轮询研判结果。' }),
  operation({ operationId: 'profile-analyze', group: 'profile', label: '触发 AI 研判', method: 'POST', path: '/profile/{source_id}/analyze', description: '启动异步研判。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'courses-list', group: 'chat', label: '课程列表', method: 'GET', path: '/client/courses', description: '经安全代理查询课程。' }),
  operation({ operationId: 'courses-detail', group: 'chat', label: '课程详情', method: 'GET', path: '/client/courses/{course_id}', description: '经安全代理查询课程。' }),
  operation({ operationId: 'events-list', group: 'chat', label: '活动列表', method: 'GET', path: '/client/events', description: '经安全代理查询活动。' }),
  operation({ operationId: 'events-detail', group: 'chat', label: '活动详情', method: 'GET', path: '/client/events/{event_id}', description: '经安全代理查询活动。' }),
  operation({ operationId: 'events-register', group: 'chat', label: '活动报名', method: 'POST', path: '/client/events/{event_id}/register', description: '经安全代理报名。', defaultBody: { remark: '' }, requiresConfirmation: true }),
  operation({ operationId: 'events-cancel', group: 'chat', label: '取消报名', method: 'DELETE', path: '/client/events/{event_id}/register', description: '经安全代理取消报名。', requiresConfirmation: true }),
  operation({ operationId: 'chat-session-create', group: 'chat', label: '创建会话', method: 'POST', path: '/client/chat/sessions', description: '经安全代理创建会话。', defaultBody: {} }),
  operation({ operationId: 'chat-session-detail', group: 'chat', label: '会话详情', method: 'GET', path: '/client/chat/sessions/{session_id}', description: '读取会话信息。' }),
  operation({ operationId: 'chat-messages-list', group: 'chat', label: '消息历史', method: 'GET', path: '/client/chat/sessions/{session_id}/messages', description: '读取消息。' }),
  operation({ operationId: 'chat-message-create', group: 'chat', label: '保存消息', method: 'POST', path: '/client/chat/sessions/{session_id}/messages', description: '写入会话消息。', defaultBody: { role: 'user', content: '' }, requiresConfirmation: true }),
  operation({ operationId: 'student-ticket-update', group: 'student', label: '处理投诉工单', method: 'PATCH', path: '/student/feedback-tickets/{ticket_id}', description: '更新工单状态。', defaultBody: { status: 'processing' }, requiresConfirmation: true }),
  operation({ operationId: 'report-action-proxy-detail', group: 'reports', label: '报告行动详情（兼容接口）', method: 'GET', path: '/report-actions/{action_id}', description: '读取已有报告行动，便于兼容已合并的行动接口。' }),
  operation({ operationId: 'report-action-proxy-update', group: 'reports', label: '更新报告行动（兼容接口）', method: 'PATCH', path: '/report-actions/{action_id}', description: '更新已有报告行动，便于兼容已合并的行动接口。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'report-types', group: 'reports', label: '报告类型', method: 'GET', path: '/reports/types', description: '读取报告类型。' }),
  operation({ operationId: 'report-generate', group: 'reports', label: '生成报告', method: 'POST', path: '/reports/generate', description: '提交异步报告。', defaultBody: { report_type: '' }, requiresConfirmation: true }),
  operation({ operationId: 'report-list', group: 'reports', label: '报告列表', method: 'GET', path: '/reports', description: '查询报告。' }),
  operation({ operationId: 'report-detail', group: 'reports', label: '报告详情', method: 'GET', path: '/reports/{report_id}', description: '读取报告详情。' }),
  operation({ operationId: 'report-retry', group: 'reports', label: '重试报告', method: 'POST', path: '/reports/{report_id}/retry', description: '重试失败报告。', requiresConfirmation: true }),
  operation({ operationId: 'report-action-create', group: 'reports', label: '创建报告行动', method: 'POST', path: '/reports/{report_id}/actions', description: '创建行动项。', defaultBody: { title: '' }, requiresConfirmation: true }),
  operation({ operationId: 'report-actions-list', group: 'reports', label: '报告行动列表', method: 'GET', path: '/reports/{report_id}/actions', description: '查询报告行动。' }),
  operation({ operationId: 'report-action-update', group: 'reports', label: '更新报告行动', method: 'PATCH', path: '/reports/actions/{action_id}', description: '更新行动项。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'schedules-create', group: 'reports', label: '创建报告计划', method: 'POST', path: '/report-schedules', description: '创建计划。', defaultBody: { report_type: '', schedule_type: 'manual' }, requiresConfirmation: true }),
  operation({ operationId: 'schedules-list', group: 'reports', label: '报告计划列表', method: 'GET', path: '/report-schedules', description: '查询计划。' }),
  operation({ operationId: 'schedules-detail', group: 'reports', label: '报告计划详情', method: 'GET', path: '/report-schedules/{schedule_id}', description: '读取计划。' }),
  operation({ operationId: 'schedules-update', group: 'reports', label: '更新报告计划', method: 'PATCH', path: '/report-schedules/{schedule_id}', description: '更新计划。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'schedules-delete', group: 'reports', label: '删除报告计划', method: 'DELETE', path: '/report-schedules/{schedule_id}', description: '删除计划。', requiresConfirmation: true }),
  operation({ operationId: 'application-materials-list', group: 'reportData', label: '申请材料列表', method: 'GET', path: '/report-data/application-materials', description: '读取申请材料数据。' }),
  operation({ operationId: 'application-materials-create', group: 'reportData', label: '新增申请材料', method: 'POST', path: '/report-data/application-materials', description: '新增申请材料数据。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'channel-costs-list', group: 'reportData', label: '渠道成本列表', method: 'GET', path: '/report-data/channel-costs', description: '读取渠道成本数据。' }),
  operation({ operationId: 'channel-costs-create', group: 'reportData', label: '新增渠道成本', method: 'POST', path: '/report-data/channel-costs', description: '新增渠道成本数据。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'contracts-list', group: 'reportData', label: '合同列表', method: 'GET', path: '/report-data/contracts', description: '读取合同数据。' }),
  operation({ operationId: 'contracts-create', group: 'reportData', label: '新增合同', method: 'POST', path: '/report-data/contracts', description: '新增合同数据。', defaultBody: {}, requiresConfirmation: true }),
  operation({ operationId: 'payments-list', group: 'reportData', label: '回款列表', method: 'GET', path: '/report-data/payments', description: '读取回款数据。' }),
  operation({ operationId: 'payments-create', group: 'reportData', label: '新增回款', method: 'POST', path: '/report-data/payments', description: '新增回款数据。', defaultBody: {}, requiresConfirmation: true }),
]

export const apiGroups: Array<{ id: ApiGroup; label: string }> = [
  { id: 'auth', label: '认证与组织' }, { id: 'crm', label: 'CRM 与日报' }, { id: 'profile', label: '客户研判' },
  { id: 'chat', label: '客服与活动' }, { id: 'student', label: '学生服务' }, { id: 'reports', label: '报告中心' }, { id: 'reportData', label: '报告数据维护' },
]
