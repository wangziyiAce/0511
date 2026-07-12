/**
 * 页面标题栏组件。
 *
 * 职责：统一管理所有页面顶部的标题、描述和操作按钮区域。
 */

import { cn } from '@/lib/utils'

interface PageHeaderProps {
  title: string
  description?: string
  children?: React.ReactNode
  className?: string
}

export default function PageHeader({ title, description, children, className }: PageHeaderProps) {
  return (
    <header className={cn('editorial-header mb-6', className)}>
      <div>
        <p className="editorial-kicker">Service archive</p>
        <h1 className="editorial-title">{title}</h1>
        {description && (
          <p className="editorial-description">{description}</p>
        )}
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </header>
  )
}
