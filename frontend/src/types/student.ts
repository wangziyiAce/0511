export interface FeedbackTicketUpdate { status: string; handler_id?: number; handle_result?: string }
export interface FeedbackTicket { id?: number; ticket_id?: number; status: string; handler_id?: number | null; handle_result?: string | null; [key: string]: unknown }
