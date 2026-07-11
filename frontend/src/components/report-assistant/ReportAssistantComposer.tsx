/**
 * 智能报告助手 — 消息输入区域组件。
 *
 * 职责：
 * 1. 提供文本输入框和发送按钮
 * 2. 支持 Enter 发送，Shift+Enter 换行
 * 3. 发送中禁用输入，防止重复提交
 * 4. 不允许空消息提交
 */

import { useState, useRef, type KeyboardEvent } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  /** 发送消息回调 */
  onSend: (text: string) => void
  /** 是否正在发送中 */
  disabled?: boolean
  /** 占位提示文本 */
  placeholder?: string
}

export default function ReportAssistantComposer({ onSend, disabled, placeholder }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return

    onSend(trimmed)
    setText('')

    // 发送后重新聚焦输入框
    setTimeout(() => {
      inputRef.current?.focus()
    }, 0)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter 发送（不含 Shift）
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex items-end gap-2 border-t bg-background p-3">
      <textarea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || '输入消息...'}
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        maxLength={2000}
      />
      <Button
        size="sm"
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="shrink-0"
        aria-label="发送消息"
      >
        {disabled ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </div>
  )
}
