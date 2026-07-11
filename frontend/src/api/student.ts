import apiClient from '@/lib/api-client'
import type { FeedbackTicket, FeedbackTicketUpdate } from '@/types/student'

interface Envelope<T> { code: number; message: string; data: T }
export async function updateFeedbackTicket(ticketId: number, data: FeedbackTicketUpdate) {
  const response = await apiClient.patch<Envelope<FeedbackTicket>>(`/student/feedback-tickets/${ticketId}`, data)
  return response.data.data
}
