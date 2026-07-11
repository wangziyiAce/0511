/**
 * 单个接口的联调表单。
 * 上游工作台传入目录操作与当前表单状态；本组件收集路径、查询和请求体，展示 Loading、
 * 权限提示以及响应检查器。真正的 Axios 调用留在页面层，便于今后替换为 React Query。
 */
import { Play, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ApiOperation } from '@/api/operation-catalog'
import { ResponseInspector } from './ResponseInspector'

interface ApiOperationPanelProps {
  operation: ApiOperation
  pathValues: Record<string, string>
  queryText: string
  bodyText: string
  loading: boolean
  result: unknown
  error: string | null
  onPathValueChange: (name: string, value: string) => void
  onQueryTextChange: (value: string) => void
  onBodyTextChange: (value: string) => void
  onExecute: () => void
}

const placeholders = (path: string) => [...path.matchAll(/\{([^}]+)\}/g)].map((match) => match[1])

export function ApiOperationPanel({
  operation, pathValues, queryText, bodyText, loading, result, error,
  onPathValueChange, onQueryTextChange, onBodyTextChange, onExecute,
}: ApiOperationPanelProps) {
  return <section className="space-y-5 rounded-xl border border-border bg-card p-5">
    <div>
      <div className="flex items-center gap-2"><span className="rounded bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-700">{operation.method}</span><code className="text-sm">/api/v1{operation.path}</code></div>
      <p className="mt-2 text-sm text-muted-foreground">{operation.description}</p>
      {operation.serverOnly && <p className="mt-2 flex items-center gap-2 text-sm text-warning"><ShieldAlert className="h-4 w-4" />该操作只允许服务端工作流调用。</p>}
    </div>
    {placeholders(operation.path).map((name) => <div key={name}><Label htmlFor={name}>路径参数：{name}</Label><Input id={name} value={pathValues[name] ?? ''} onChange={(event) => onPathValueChange(name, event.target.value)} /></div>)}
    <div><Label htmlFor="query">查询参数 JSON</Label><textarea id="query" className="mt-1 min-h-20 w-full rounded-md border border-input bg-background p-3 font-mono text-sm" value={queryText} onChange={(event) => onQueryTextChange(event.target.value)} /></div>
    {!['GET', 'DELETE'].includes(operation.method) && <div><Label htmlFor="body">{operation.requestKind === 'multipart' ? '表单字段 JSON（将自动转为 multipart）' : '请求体 JSON'}</Label><textarea id="body" className="mt-1 min-h-44 w-full rounded-md border border-input bg-background p-3 font-mono text-sm" value={bodyText} onChange={(event) => onBodyTextChange(event.target.value)} /></div>}
    <Button onClick={onExecute} disabled={loading || operation.serverOnly}><Play className="mr-2 h-4 w-4" />{loading ? '请求中…' : '执行真实请求'}</Button>
    <ResponseInspector result={result} error={error} />
  </section>
}
