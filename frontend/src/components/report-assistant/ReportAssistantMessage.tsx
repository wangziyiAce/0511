/**
 * 智能报告助手 — 单条消息组件。
 *
 * 展示一条对话消息，区分 user / assistant / system 三种角色。
 * assistant 消息可以包含：
 * - 回答文本
 * - 生成中状态提示
 * - 数据质量提示
 * - 证据卡片
 * - 建议追问按钮
 * - 报告 ID 跳转链接
 * - 澄清问题
 * - 错误提示
 */

import { Link } from 'react-router-dom'
import { Bot, User, Loader2, ExternalLink, AlertCircle, ShieldAlert } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import ReportAssistantDataQuality from './ReportAssistantDataQuality'
import ReportAssistantEvidence from './ReportAssistantEvidence'
import ReportAssistantSuggestions from './ReportAssistantSuggestions'
import ReportAssistantComparison from './ReportAssistantComparison'
import ReportAssistantRelationship from './ReportAssistantRelationship'
import type { AssistantMessage } from '@/types/report-assistant'

interface Props {
  /** 消息对象 */
  message: AssistantMessage
  /** 建议追问点击回调 */
  onFollowUp?: (text: string) => void
  /** 是否正在发送中（禁用追问按钮） */
  isSending?: boolean
}

export default function ReportAssistantMessage({ message, onFollowUp, isSending }: Props) {
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'
  const isSystem = message.role === 'system'

  // 系统消息
  if (isSystem) {
    return (
      <div className="flex justify-center py-2">
        <span className="text-xs text-muted-foreground bg-muted px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* 头像 */}
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
        isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
      }`}>
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* 消息内容 */}
      <div className={`flex-1 space-y-1 ${isUser ? 'flex flex-col items-end' : ''}`}>
        <Card className={`inline-block max-w-[85%] px-3 py-2 text-sm ${
          isUser ? 'bg-primary text-primary-foreground' : ''
        }`}>
          {/* 加载中 */}
          {isAssistant && message.status === 'generating' && (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>正在处理...</span>
            </div>
          )}

          {/* 生成中状态 */}
          {isAssistant && message.status === 'generating' && message.reportId && (
            <div className="mt-2 space-y-2">
              <p className="text-xs">已创建报告任务，正在后台生成。</p>
              {message.reportType && (
                <p className="text-xs text-muted-foreground">报告类型: {message.reportType}</p>
              )}
              {message.assumptions && message.assumptions.length > 0 && (
                <div className="text-xs text-muted-foreground">
                  <span>时间假设: </span>
                  {message.assumptions.map((a, i) => (
                    <span key={i} className="mr-2">· {a}</span>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                {message.reportId && (
                  <Link to={`/reports/${message.reportId}`}>
                    <Button variant="outline" size="sm" className="h-7 text-xs">
                      <ExternalLink className="mr-1 h-3 w-3" />
                      查看报告详情
                    </Button>
                  </Link>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                提示：你可以问"报告生成好了吗？"来检查状态
              </p>
            </div>
          )}

          {/* 正常完成的消息 */}
          {isAssistant && message.status === 'completed' && (
            <>
              <div className="whitespace-pre-wrap">{message.content}</div>

              {/* 报告跳转链接 */}
              {message.reportId && (
                <div className="mt-2">
                  <Link to={`/reports/${message.reportId}`}>
                    <Button variant="outline" size="sm" className="h-7 text-xs">
                      <ExternalLink className="mr-1 h-3 w-3" />
                      查看完整报告
                    </Button>
                  </Link>
                </div>
              )}
            </>
          )}

          {/* 澄清问题 */}
          {isAssistant && message.status === 'needs_clarification' && (
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            </div>
          )}

          {/* 权限不足 */}
          {isAssistant && message.status === 'permission_denied' && (
            <div className="flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
              <div>
                <p className="font-medium text-destructive">权限不足</p>
                <p className="text-xs text-muted-foreground mt-1">{message.content}</p>
              </div>
            </div>
          )}

          {/* 未找到 */}
          {isAssistant && message.status === 'not_found' && (
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
                <div>
                  <p className="font-medium">报告不存在</p>
                  <p className="text-xs text-muted-foreground mt-1">{message.content}</p>
                </div>
              </div>
            </div>
          )}

          {/* 错误 */}
          {isAssistant && message.status === 'error' && (
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
              <div>
                <p className="font-medium text-destructive">处理出错</p>
                <p className="text-xs text-muted-foreground mt-1">{message.content}</p>
              </div>
            </div>
          )}

          {/* 用户消息 */}
          {isUser && <div className="whitespace-pre-wrap">{message.content}</div>}
        </Card>

        {/* assistant 消息的附加内容（只在 completed 状态展示） */}
        {isAssistant && message.status === 'completed' && (
          <>
            {/* Iteration 3：比较表格（permission_denied 时隐藏） */}
            {'comparison' in message && (message as any).comparison && (
              <ReportAssistantComparison
                items={(message as any).comparison}
                currentLabel={(message as any).comparison_period?.current_label}
                previousLabel={(message as any).comparison_period?.previous_label}
              />
            )}

            {/* Iteration 3：关系分析区块（permission_denied 时隐藏） */}
            {'relationship_sections' in message && (message as any).relationship_sections && (
              <ReportAssistantRelationship
                sections={(message as any).relationship_sections}
              />
            )}

            {/* 数据质量提示 */}
            <ReportAssistantDataQuality dataQuality={message.dataQuality} />

            {/* 证据卡片 */}
            <ReportAssistantEvidence evidence={message.evidence || []} />

            {/* 建议追问 */}
            {onFollowUp && (
              <ReportAssistantSuggestions
                suggestions={message.suggestedFollowUps || []}
                onSelect={onFollowUp}
                disabled={isSending}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
