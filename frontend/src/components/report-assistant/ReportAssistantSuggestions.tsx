/**
 * 智能报告助手 — 建议追问按钮组件。
 *
 * 将后端返回的 suggested_follow_ups 渲染为可点击的 Chips。
 * 点击后直接发送对应文本，使用当前 conversation_context，
 * 生成新的 client_request_id。
 *
 * 不在前端自行解释追问含义。
 */

import { Button } from '@/components/ui/button'
import { MessageSquare } from 'lucide-react'

interface Props {
  /** 建议追问文本列表 */
  suggestions: string[]
  /** 点击追问回调 */
  onSelect: (text: string) => void
  /** 是否禁用（发送中时禁用） */
  disabled?: boolean
}

export default function ReportAssistantSuggestions({ suggestions, onSelect, disabled }: Props) {
  if (!suggestions || suggestions.length === 0) return null

  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">建议追问</p>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((text, index) => (
          <Button
            key={index}
            variant="outline"
            size="sm"
            className="h-7 px-2.5 text-xs"
            disabled={disabled}
            onClick={() => onSelect(text)}
          >
            <MessageSquare className="mr-1 h-3 w-3" />
            {text}
          </Button>
        ))}
      </div>
    </div>
  )
}
