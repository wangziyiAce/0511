/**
 * 全接口联调工作台页面。
 * 该页面以接口目录为唯一操作入口：用户选择操作、填写参数后调用真实 FastAPI，写操作则先
 * 经过二次确认。首版优先保证每个可调用后端操作有入口与排错输出，后续业务页可渐进替换。
 */
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiOperationPanel } from '@/components/api/ApiOperationPanel'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { apiGroups, apiOperations, type ApiOperation } from '@/api/operation-catalog'
import { runOperation } from '@/api/operation-runner'

export default function ApiWorkbenchPage() {
  const { group = 'auth' } = useParams()
  const currentGroup = apiGroups.find((item) => item.id === group) ?? apiGroups[0]
  const operations = useMemo(() => apiOperations.filter((item) => item.group === currentGroup.id), [currentGroup.id])
  const [selectedId, setSelectedId] = useState(operations[0]?.operationId ?? '')
  const selected = operations.find((item) => item.operationId === selectedId) ?? operations[0]
  const [pathValues, setPathValues] = useState<Record<string, string>>({})
  const [queryText, setQueryText] = useState(JSON.stringify(selected?.defaultQuery ?? {}, null, 2))
  const [bodyText, setBodyText] = useState(JSON.stringify(selected?.defaultBody ?? {}, null, 2))
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const selectOperation = (operation: ApiOperation) => {
    setSelectedId(operation.operationId)
    setPathValues({})
    setQueryText(JSON.stringify(operation.defaultQuery ?? {}, null, 2))
    setBodyText(JSON.stringify(operation.defaultBody ?? {}, null, 2))
    setResult(null)
    setError(null)
  }

  /**
   * 解析工作台输入并调用统一 API Client。
   * JSON 不合法时不会发出网络请求；服务端 401/403/422/5xx 则由现有响应拦截器和检查器共同反馈。
   */
  const execute = async () => {
    if (!selected) return
    try {
      const query = JSON.parse(queryText) as Record<string, string>
      const body = bodyText.trim() ? JSON.parse(bodyText) as Record<string, unknown> : undefined
      setLoading(true)
      setError(null)
      setResult(await runOperation(selected, { pathValues, query, body }))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '请求参数不是有效 JSON，或接口调用失败。')
    } finally {
      setLoading(false)
      setConfirmOpen(false)
    }
  }

  /** 写操作必须经弹窗确认；读操作可以直接执行，减少首轮只读联调的阻力。 */
  const requestExecution = () => {
    if (!selected) return
    if (selected.requiresConfirmation) {
      setConfirmOpen(true)
      return
    }
    void execute()
  }

  if (!selected) return <div className="p-6">当前分组暂无可执行操作。</div>

  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="border-b border-brand-200 pb-5">
      <p className="text-xs tracking-[0.2em] text-brand-600">API WORKBENCH</p>
      <h1 className="mt-2 text-2xl font-semibold">{currentGroup.label}</h1>
      <p className="mt-1 text-sm text-muted-foreground">首版真实接口联调入口。状态取决于当前登录用户、后端数据和服务可用性。</p>
    </header>
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <aside className="space-y-2">{operations.map((operation) => <button key={operation.operationId} onClick={() => selectOperation(operation)} className={`w-full rounded-lg border p-3 text-left ${operation.operationId === selected.operationId ? 'border-brand-600 bg-brand-50' : 'border-border bg-card'}`}><span className="text-xs font-semibold text-brand-600">{operation.method}</span><p className="mt-1 text-sm font-medium">{operation.label}</p><p className="mt-1 text-xs text-muted-foreground">{operation.path}</p></button>)}</aside>
      <ApiOperationPanel
        operation={selected}
        pathValues={pathValues}
        queryText={queryText}
        bodyText={bodyText}
        loading={loading}
        result={result}
        error={error}
        onPathValueChange={(name, value) => setPathValues((current) => ({ ...current, [name]: value }))}
        onQueryTextChange={setQueryText}
        onBodyTextChange={setBodyText}
        onExecute={requestExecution}
      />
    </div>
    <WriteConfirmDialog open={confirmOpen} operationLabel={selected.label} submitting={loading} onOpenChange={setConfirmOpen} onConfirm={() => void execute()} />
  </div>
}
