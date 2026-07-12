import apiClient from '@/lib/api-client'
import type { CustomerSource, ProfileDetail, ProfileRule, SourcePage } from '@/types/profile'

interface Envelope<T> { code: number; message: string; data: T }
const unwrap = <T>(response: { data: Envelope<T> }) => response.data.data

/** 上传文件或文本资料；字段名与 FastAPI Form 契约保持一致。 */
export function uploadCustomerSource(input: { source_type: string; content_text?: string; file?: File }) {
  const data = new FormData()
  data.append('source_type', input.source_type)
  if (input.content_text) data.append('content_text', input.content_text)
  if (input.file) data.append('file', input.file)
  return apiClient.post<Envelope<{ source_id: number; parse_status: string }>>('/profile/upload', data, { headers: { 'Content-Type': undefined } }).then(unwrap)
}
export function getCustomerSources(params: { page?: number; page_size?: number; parse_status?: string } = {}) { return apiClient.get<Envelope<SourcePage>>('/profile/sources', { params }).then(unwrap) }
export function getProfileDetail(sourceId: number) { return apiClient.get<Envelope<ProfileDetail>>(`/profile/${sourceId}`).then(unwrap) }
export function analyzeProfile(sourceId: number, rule_id?: number) { return apiClient.post<Envelope<{ source_id: number; parse_status: string }>>(`/profile/${sourceId}/analyze`, rule_id ? { rule_id } : {}).then(unwrap) }
export function getProfileRules() { return apiClient.get<Envelope<{ items: ProfileRule[] }>>('/profile/rules').then(unwrap).then((data) => data.items) }
export function createProfileRule(data: { product_line: string; rule_name: string; rule_content: Record<string, unknown>; priority?: number }) { return apiClient.post<Envelope<ProfileRule>>('/profile/rules', data).then(unwrap) }
export function updateProfileRule(ruleId: number, data: Partial<Pick<ProfileRule, 'status' | 'priority' | 'rule_name' | 'product_line' | 'rule_content'>>) { return apiClient.put<Envelope<ProfileRule>>(`/profile/rules/${ruleId}`, data).then(unwrap) }
export type { CustomerSource }
