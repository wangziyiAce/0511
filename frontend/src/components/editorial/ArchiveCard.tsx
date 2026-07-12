import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface ArchiveCardProps extends HTMLAttributes<HTMLElement> {
  title?: string
  index?: string
  action?: ReactNode
}

/** 档案卡片用于承载表单、列表与摘要，装饰线不干扰核心数据阅读。 */
export function ArchiveCard({ title, index, action, className, children, ...props }: ArchiveCardProps) {
  return <section className={cn('archive-card', className)} {...props}>
    {(title || action) && <header className="archive-card__header">
      <div>{index && <span className="archive-index">{index}</span>}{title && <h2>{title}</h2>}</div>
      {action}
    </header>}
    <div className="archive-card__body">{children}</div>
  </section>
}
