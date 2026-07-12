import apiClient from '@/lib/api-client'
import type { ChatMessage, ChatSession, Course, EventItem, Page } from '@/types/service'

interface Envelope<T> { code: number; message: string; data: T }
const unwrap = <T>(response: { data: Envelope<T> }) => response.data.data

export function getCourses(params: { keyword?: string; category?: string; page?: number; page_size?: number } = {}) { return apiClient.get<Envelope<Page<Course>>>('/client/courses', { params }).then(unwrap) }
export function getEvents(params: { status?: string; page?: number; page_size?: number } = {}) { return apiClient.get<Envelope<Page<EventItem>>>('/client/events', { params }).then(unwrap) }
export function registerEvent(eventId: number, remark?: string) { return apiClient.post<Envelope<{ id: number; status: string }>>(`/client/events/${eventId}/register`, { remark }).then(unwrap) }
export function cancelEvent(eventId: number) { return apiClient.delete<Envelope<{ id: number; status: string }>>(`/client/events/${eventId}/register`).then(unwrap) }
export function createChatSession() { return apiClient.post<Envelope<ChatSession>>('/client/chat/sessions', {}).then(unwrap) }
export function getChatMessages(sessionId: string) { return apiClient.get<Envelope<{ items: ChatMessage[]; next_cursor?: number | null; has_more: boolean }>>(`/client/chat/sessions/${sessionId}/messages`, { params: { limit: 50 } }).then(unwrap) }
export function createChatMessage(sessionId: string, content: string) { return apiClient.post<Envelope<ChatMessage>>(`/client/chat/sessions/${sessionId}/messages`, { role: 'user', content }).then(unwrap) }
