/**
 * 通用接口执行器。
 *
 * 页面层只提供操作目录、路径参数、查询参数和 JSON 请求体；本文件负责把这些
 * 输入组装为 Axios 请求，从而避免每个首版联调页面重复维护相同的请求逻辑。
 */
import apiClient from '@/lib/api-client'
import type { ApiOperation } from './operation-catalog'

export interface OperationInput {
  pathValues: Record<string, string>
  query: Record<string, string>
  body?: Record<string, unknown>
}

export async function runOperation(operation: ApiOperation, input: OperationInput): Promise<unknown> {
  const path = operation.path.replace(/\{([^}]+)\}/g, (_, key: string) => encodeURIComponent(input.pathValues[key] ?? `{${key}}`))
  const shouldSendBody = !['GET', 'DELETE'].includes(operation.method)

  // 资料上传接口由 FastAPI Form 接收。浏览器侧只传普通登录态，文件和服务密钥均不进入前端代码。
  const data = operation.requestKind === 'multipart' && input.body
    ? toFormData(input.body)
    : shouldSendBody ? input.body : undefined

  const response = await apiClient.request<unknown>({
    method: operation.method,
    url: path,
    params: Object.fromEntries(Object.entries(input.query).filter(([, value]) => value.trim())),
    data,
    // 覆盖客户端默认 JSON Header，让 Axios 为 FormData 自动补齐 multipart boundary。
    headers: operation.requestKind === 'multipart' ? { 'Content-Type': undefined } : undefined,
  })
  return response.data
}

/**
 * 把工作台 JSON 编辑器中的字段转成浏览器表单数据。
 * 简单值原样传递，对象或数组序列化，便于首版先联调文本资料和扩展字段。
 */
function toFormData(body: Record<string, unknown>): FormData {
  const formData = new FormData()
  for (const [key, value] of Object.entries(body)) {
    if (value === undefined || value === null) continue
    formData.append(key, typeof value === 'string' ? value : JSON.stringify(value))
  }
  return formData
}
