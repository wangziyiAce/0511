/** 客服中心：真实会话档案与课程/活动资料库，所有请求只经过 client 安全代理。 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, CalendarDays, MessageSquareText, Send } from 'lucide-react'
import { toast } from 'sonner'
import { cancelEvent, createChatMessage, createChatSession, getChatMessages, getCourses, getEvents, registerEvent } from '@/api/customer-service'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { StatusStamp } from '@/components/editorial/StatusStamp'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
const timeFormatter = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' })

export default function CustomerServicePage() {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState(() => sessionStorage.getItem('customer-service-session') || '')
  const [message, setMessage] = useState('')
  const [keyword, setKeyword] = useState('')
  const [confirmAction, setConfirmAction] = useState<{ label: string; run: () => void } | null>(null)
  const coursesQuery = useQuery({ queryKey: ['service', 'courses', keyword], queryFn: () => getCourses({ keyword: keyword || undefined, page: 1, page_size: 20 }) })
  const eventsQuery = useQuery({ queryKey: ['service', 'events'], queryFn: () => getEvents({ status: 'upcoming', page: 1, page_size: 20 }) })
  const messagesQuery = useQuery({ queryKey: ['service', 'messages', sessionId], queryFn: () => getChatMessages(sessionId), enabled: Boolean(sessionId) })
  const sessionMutation = useMutation({ mutationFn: createChatSession, onSuccess: (session) => { setSessionId(session.session_id); sessionStorage.setItem('customer-service-session', session.session_id) } })
  const messageMutation = useMutation({ mutationFn: (content: string) => createChatMessage(sessionId, content), onSuccess: async () => { setMessage(''); await queryClient.invalidateQueries({ queryKey: ['service', 'messages', sessionId] }) } })
  const eventMutation = useMutation({ mutationFn: ({ eventId, cancel }: { eventId: number; cancel: boolean }) => cancel ? cancelEvent(eventId) : registerEvent(eventId), onSuccess: async (result) => { toast.success(result.status === 'cancelled' ? '已取消报名' : '报名已提交'); await queryClient.invalidateQueries({ queryKey: ['service', 'events'] }) } })
  useEffect(() => { if (!sessionId && !sessionMutation.isPending && !sessionMutation.isError) sessionMutation.mutate() }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps
  const writing = messageMutation.isPending || eventMutation.isPending

  return <div className="space-y-6">
    <EditorialPageHeader eyebrow="Knowledge salon · conversation archive" title="客服中心" description="保存咨询对话，在同一工作区查找课程与近期活动。当前后端仅负责会话归档，不虚构尚未返回的 AI 回答。" />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]">
      <ArchiveCard title="咨询会话" index="CONVERSATION" className="min-w-0">
        <div className="flex min-h-[460px] min-w-0 flex-col" aria-busy={sessionMutation.isPending || messagesQuery.isLoading}>
          {sessionMutation.isPending && <LoadingState text="正在建立安全会话…" />}{sessionMutation.isError && <ErrorState title="无法建立会话" onRetry={() => sessionMutation.mutate()} />}
          <div aria-live="polite" className="flex-1 space-y-3 overflow-y-auto pr-1">{messagesQuery.isLoading && <LoadingState />}{messagesQuery.isError && <ErrorState onRetry={() => messagesQuery.refetch()} />}{messagesQuery.data?.items.length === 0 && <EmptyState icon={<MessageSquareText className="h-8 w-8" />} title="开始一次咨询" description="消息会保存到当前账号的会话档案中。" />}{messagesQuery.data?.items.map((item) => <div key={item.id} className={`max-w-[85%] border p-3 text-sm leading-6 ${item.role === 'user' ? 'ml-auto border-wine/30 bg-wine/5' : 'border-bronze/40 bg-paper'}`}><p className="break-words">{item.content}</p><p className="mt-1 text-[10px] text-muted-foreground">{item.role === 'user' ? '我' : '客服'} · {timeFormatter.format(new Date(item.create_time))}</p></div>)}</div>
          <form className="mt-5 flex flex-col gap-2 border-t border-bronze/30 pt-4 sm:flex-row" onSubmit={(event) => { event.preventDefault(); if (message.trim() && sessionId) messageMutation.mutate(message.trim()) }}><label htmlFor="service-message" className="sr-only">咨询内容</label><Input id="service-message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="输入需要记录的咨询问题" aria-describedby="service-message-hint" /><span id="service-message-hint" className="sr-only">消息将保存到当前账号的咨询档案</span><Button className="sm:w-auto" type="submit" disabled={!sessionId || !message.trim() || messageMutation.isPending} aria-label="发送消息"><Send /><span className="sm:sr-only">发送消息</span></Button></form>
          {messageMutation.isError && <div className="mt-3" role="status"><ErrorState title="消息保存失败" message="请检查网络连接后重试，已输入内容不会被清除。" /></div>}
        </div>
      </ArchiveCard>
      <div className="space-y-6">
        <ArchiveCard title="课程索引" index="COURSES"><Input aria-label="搜索课程" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="按名称或关键词搜索" />{coursesQuery.isLoading && <LoadingState />}{coursesQuery.isError && <ErrorState onRetry={() => coursesQuery.refetch()} />}{coursesQuery.data?.items.length === 0 && <EmptyState icon={<BookOpen className="h-7 w-7" />} title="暂无匹配课程" description={keyword ? '请调整关键词后重新搜索。' : '课程资料同步后会显示在这里。'} />}<div className="mt-4 space-y-3">{coursesQuery.data?.items.map((course) => <article key={course.id} className="min-w-0 border-l-2 border-bronze pl-3"><div className="flex min-w-0 items-start justify-between gap-2"><h3 className="min-w-0 break-words text-sm font-medium">{course.project_name}</h3><BookOpen className="h-4 w-4 shrink-0 text-wine" aria-hidden /></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{course.description || course.target_audience || '暂无课程简介'}</p><p className="mt-2 font-mono text-xs">{course.duration || '时长待定'} · {course.price ?? '价格待定'}</p></article>)}</div></ArchiveCard>
        <ArchiveCard title="近期活动" index="EVENTS">{eventsQuery.isLoading && <LoadingState />}{eventsQuery.isError && <ErrorState onRetry={() => eventsQuery.refetch()} />}{eventsQuery.data?.items.length === 0 && <EmptyState icon={<CalendarDays className="h-7 w-7" />} title="暂无近期活动" description="新活动发布后会显示在这里。" />}<div className="space-y-3">{eventsQuery.data?.items.map((item) => <article key={item.id} className="min-w-0 border border-bronze/30 p-3"><div className="flex min-w-0 items-start justify-between gap-2"><div className="min-w-0"><h3 className="break-words text-sm font-medium">{item.event_name}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground"><CalendarDays className="mr-1 inline h-3 w-3" aria-hidden />{dateTimeFormatter.format(new Date(item.start_time))} · {item.location || item.event_type}</p></div><StatusStamp label={item.status} tone="info" /></div><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" disabled={eventMutation.isPending} onClick={() => setConfirmAction({ label: `报名“${item.event_name}”`, run: () => eventMutation.mutate({ eventId: item.id, cancel: false }) })}>报名</Button><Button size="sm" variant="outline" disabled={eventMutation.isPending} onClick={() => setConfirmAction({ label: `取消“${item.event_name}”报名`, run: () => eventMutation.mutate({ eventId: item.id, cancel: true }) })}>取消报名</Button></div></article>)}</div></ArchiveCard>
      </div>
    </div>
    <WriteConfirmDialog open={Boolean(confirmAction)} operationLabel={confirmAction?.label || '活动操作'} submitting={writing} onOpenChange={(open) => { if (!open) setConfirmAction(null) }} onConfirm={() => { confirmAction?.run(); setConfirmAction(null) }} />
  </div>
}
