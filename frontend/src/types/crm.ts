/** 企业工作台领域类型：与 CRM、跟进和日报 FastAPI Schema 对齐。 */
export type LeadStatus = 'new' | 'contacting' | 'qualified' | 'signed' | 'lost'
export type FollowUpType = 'phone' | 'wechat' | 'meeting' | 'email' | 'other'

export interface LeadResponse {
  id: number; customer_name: string; contact_info: string | null; status: LeadStatus
  intended_country: string | null; intended_major: string | null; source_channel: string | null
  remark: string | null; owner_employee_id: number | null; owner_name: string | null
  last_contact_time: string | null; create_time: string | null
}
export interface LeadListResponse { items: LeadResponse[]; total: number; page: number; page_size: number }
export interface LeadCreate { customer_name: string; contact_info?: string; intended_country?: string; intended_major?: string; source_channel?: string; remark?: string; owner_employee_id: number }
export interface LeadStatusUpdate { status: LeadStatus; lost_reason?: string }
export interface FollowUpCreate { employee_id: number; follow_type: FollowUpType; content: string; next_plan?: string }
export interface FollowUpResponse { id: number; lead_id: number; employee_id: number; follow_type: string; content: string; next_plan: string | null; create_time: string | null }
export interface DailyReportCreate { employee_id: number; report_date: string; status: 'draft' | 'submitted'; content: string; raw_content?: string; key_progress?: string[]; risks?: string[]; next_plan?: string }
export interface DailyReportResponse { id: number; employee_id: number; report_date: string; status: string; content: string; key_progress: string[] | null; risks: string[] | null; next_plan: string | null; create_time: string | null }
export interface DailyReportSummary { report_date: string; total_submitted: number; employees: Array<{ employee_id: number; key_progress: string[] | null; risks: string[] | null }> }
export interface ApiEnvelope<T> { code: number; message: string; data: T }
