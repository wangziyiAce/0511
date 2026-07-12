import type { ReactNode } from 'react'

export interface TimelineItem { id: string | number; title: string; meta?: string; content?: ReactNode }

/** 适用于跟进、分析和行动记录的纵向时间线。 */
export function Timeline({ items }: { items: TimelineItem[] }) {
  return <ol className="editorial-timeline">{items.map((item) => <li key={item.id}>
    <span className="editorial-timeline__dot" aria-hidden />
    <div><p className="font-medium text-ink">{item.title}</p>{item.meta && <p className="text-xs text-muted-foreground">{item.meta}</p>}{item.content && <div className="mt-1 text-sm">{item.content}</div>}</div>
  </li>)}</ol>
}
