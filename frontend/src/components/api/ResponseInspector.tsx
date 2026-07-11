/**
 * 接口响应检查器。
 * 首版联调需要同时看见正常响应、参数校验失败和空状态；该组件只负责呈现，不参与请求，
 * 让工作台和后续业务页可以复用同一套排错出口。
 */
interface ResponseInspectorProps {
  result: unknown
  error: string | null
}

export function ResponseInspector({ result, error }: ResponseInspectorProps) {
  return <div className="rounded-lg bg-muted p-4">
    <p className="text-sm font-medium">响应预览</p>
    {error && <pre className="mt-3 whitespace-pre-wrap text-sm text-destructive">{error}</pre>}
    {result !== null && <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(result, null, 2)}</pre>}
    {!error && result === null && <p className="mt-2 text-sm text-muted-foreground">填写参数并执行后，在此查看真实响应、空结果或服务端错误。</p>}
  </div>
}
