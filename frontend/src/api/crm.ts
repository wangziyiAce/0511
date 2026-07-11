/** 企业工作台 API：统一解开后端 { code, message, data } 信封，页面只消费领域对象。 */
import apiClient from '@/lib/api-client'
import type { ApiEnvelope, DailyReportCreate, DailyReportResponse, DailyReportSummary, FollowUpCreate, FollowUpResponse, LeadCreate, LeadListResponse, LeadResponse, LeadStatus, LeadStatusUpdate } from '@/types/crm'

const unwrap = <T>(response: { data: ApiEnvelope<T> }) => response.data.data

export function getLeads(params: { keyword?: string; status?: LeadStatus; page?: number; page_size?: number }) { return apiClient.get<ApiEnvelope<LeadListResponse>>('/crm/leads', { params }).then(unwrap) }
export function createLead(data: LeadCreate) { return apiClient.post<ApiEnvelope<LeadResponse>>('/crm/leads', data).then(unwrap) }
export function getLead(id: number) { return apiClient.get<ApiEnvelope<LeadResponse>>(`/crm/leads/${id}`).then(unwrap) }
export function updateLeadStatus(id: number, data: LeadStatusUpdate) { return apiClient.put<ApiEnvelope<LeadResponse>>(`/crm/leads/${id}/status`, data).then(unwrap) }
export function getFollowUps(leadId: number) { return apiClient.get<ApiEnvelope<FollowUpResponse[]>>(`/crm/leads/${leadId}/follow-ups`).then(unwrap) }
export function createFollowUp(leadId: number, data: FollowUpCreate) { return apiClient.post<ApiEnvelope<FollowUpResponse>>(`/crm/leads/${leadId}/follow-ups`, data).then(unwrap) }
export function getDailyReports() { return apiClient.get<ApiEnvelope<DailyReportResponse[]>>('/employee/daily-reports').then(unwrap) }
export function createDailyReport(data: DailyReportCreate) { return apiClient.post<ApiEnvelope<DailyReportResponse>>('/employee/daily-reports', data).then(unwrap) }
export function getDailySummary(reportDate: string) { return apiClient.get<ApiEnvelope<DailyReportSummary>>('/employee/daily-reports/summary', { params: { report_date: reportDate } }).then(unwrap) }
