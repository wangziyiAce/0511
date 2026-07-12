import { cn } from '@/lib/utils'

interface StatusStampProps { label: string; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }

/** 以档案印章表达状态，颜色始终辅以文字，避免只依赖颜色传达信息。 */
export function StatusStamp({ label, tone = 'neutral' }: StatusStampProps) {
  return <span className={cn('status-stamp', `status-stamp--${tone}`)}>{label}</span>
}
