export interface Course { id: number; project_name: string; category?: string | null; description?: string | null; target_audience?: string | null; price?: string | number | null; duration?: string | null; tags?: string[] | null; status: number }
export interface EventItem { id: number; event_name: string; event_type: string; description?: string | null; start_time: string; end_time?: string | null; location?: string | null; max_participants?: number | null; current_participants: number; status: string }
export interface ChatSession { id: number; session_id: string; status: string; create_time: string; last_message_time?: string | null }
export interface ChatMessage { id: number; session_id: string; role: string; content: string; intent?: string | null; create_time: string }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
