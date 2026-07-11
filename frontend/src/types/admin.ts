export interface ManagedUser { id: number; username: string; real_name: string; user_type: string; role_id?: number | null; department?: string | null; contact_info?: string | null; status: string; create_time: string }
export interface UserPage { items: ManagedUser[]; total: number; page: number; page_size: number }
export interface RoleItem { id: number; role_code: string; role_name: string; description?: string | null; status: number }
export interface UserCreateInput { username: string; password: string; real_name: string; user_type: 'student' | 'employee' | 'admin'; role_id: number; department?: string; contact_info?: string }
