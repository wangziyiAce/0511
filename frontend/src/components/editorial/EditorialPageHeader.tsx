import type { ReactNode } from 'react'

interface EditorialPageHeaderProps {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}

/** 编辑型页面统一题头：用期刊栏目、标题与说明建立稳定的信息层级。 */
export function EditorialPageHeader({ eyebrow, title, description, actions }: EditorialPageHeaderProps) {
  return <header className="editorial-header">
    <div className="min-w-0">
      <p className="editorial-kicker">{eyebrow}</p>
      <h1 className="editorial-title">{title}</h1>
      <p className="editorial-description">{description}</p>
    </div>
    {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
  </header>
}
