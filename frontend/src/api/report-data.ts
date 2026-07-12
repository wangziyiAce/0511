import apiClient from '@/lib/api-client'

export type ReportDataKind = 'application-materials' | 'channel-costs' | 'contracts' | 'payments'
export type ReportDataRecord = Record<string, string | number | boolean | null>

export function listReportData(kind: ReportDataKind) { return apiClient.get<ReportDataRecord[]>(`/report-data/${kind}`).then((response) => response.data) }
export function createReportData(kind: ReportDataKind, data: ReportDataRecord) { return apiClient.post<{ id: number }>(`/report-data/${kind}`, data).then((response) => response.data) }
