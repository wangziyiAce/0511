/**
 * 写操作二次确认弹窗。
 * 创建、更新、删除等请求会直接改变真实后端数据，因此在浏览器发出请求前要求用户显式确认；
 * 取消时不触发回调，避免工作台因误点击写入测试数据。
 */
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

interface WriteConfirmDialogProps {
  open: boolean
  operationLabel: string
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function WriteConfirmDialog({ open, operationLabel, submitting, onOpenChange, onConfirm }: WriteConfirmDialogProps) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>确认执行写操作</DialogTitle>
        <DialogDescription>“{operationLabel}”会调用真实后端并可能修改业务数据。请确认当前环境、账号权限和参数均正确。</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>取消</Button>
        <Button type="button" onClick={onConfirm} disabled={submitting}>{submitting ? '提交中…' : '确认执行'}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
}
