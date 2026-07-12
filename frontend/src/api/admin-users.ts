import apiClient from '@/lib/api-client'
import type { ManagedUser, OrganizationItem, RoleItem, UserCreateInput, UserPage } from '@/types/admin'

interface Envelope<T> { code: number; message: string; data: T }
const unwrap = <T>(response: { data: Envelope<T> }) => response.data.data
export function getUsers(params: { keyword?: string; user_type?: string; page?: number; page_size?: number } = {}) { return apiClient.get<Envelope<UserPage>>('/auth/users', { params }).then(unwrap) }
export function getRoles() { return apiClient.get<Envelope<{ items: RoleItem[] }>>('/auth/roles').then(unwrap).then((data) => data.items) }
/** 读取启用组织的平铺目录，供用户创建表单复用既有 department 字段。 */
export function getOrganizations() { return apiClient.get<Envelope<{ items: OrganizationItem[] }>>('/auth/organizations').then(unwrap).then((data) => data.items) }
export function createUser(data: UserCreateInput) { return apiClient.post<Envelope<ManagedUser>>('/auth/users', data).then(unwrap) }
