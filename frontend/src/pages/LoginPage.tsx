/** 学院门户登录：保留认证契约与恢复逻辑，仅重构视觉、校验和可访问状态。 */
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Navigate, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, LogIn, ShieldCheck } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/stores/auth-store'
import type { LoginRequest } from '@/types/auth'
import { getDefaultRoute } from '@/lib/role-navigation'
import editorialHero from '../../design-assets/mockups/b-editorial-academy/02-dashboard.png'

const loginSchema = z.object({ username: z.string().trim().min(1, '请输入用户名'), password: z.string().min(1, '请输入密码') })
type LoginFormData = z.infer<typeof loginSchema>

export default function LoginPage() {
  const navigate = useNavigate()
  const { isAuthenticated, login } = useAuthStore()
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormData>({ resolver: zodResolver(loginSchema), defaultValues: { username: '', password: '' } })
  if (isAuthenticated) return <Navigate to={getDefaultRoute(useAuthStore.getState().user?.role_code)} replace />

  const onSubmit = async (data: LoginFormData) => {
    setError(null); setIsSubmitting(true)
    try { await login(data as LoginRequest); navigate(getDefaultRoute(useAuthStore.getState().user?.role_code), { replace: true }) }
    catch (caught) { const failure = caught as { response?: { data?: { detail?: string }; status?: number } }; setError(failure.response?.status === 401 ? '用户名或密码错误。' : failure.response ? failure.response.data?.detail || '登录失败，请稍后重试。' : '无法连接服务器，请检查网络或服务状态。') }
    finally { setIsSubmitting(false) }
  }

  return <main className="grid min-h-screen bg-paper lg:grid-cols-[minmax(0,1.25fr)_minmax(420px,.75fr)]">
    <section className="relative hidden overflow-hidden bg-ink lg:block" aria-label="国际教育档案馆视觉">
      <img src={editorialHero} alt="学院建筑、地图与留学档案拼贴" width="1440" height="960" fetchPriority="high" className="absolute inset-0 h-full w-full object-cover object-left opacity-80" />
      <div className="absolute inset-0 bg-gradient-to-r from-ink/25 via-transparent to-ink/80" />
      <div className="absolute bottom-12 left-12 max-w-xl border-l-4 border-bronze bg-paper-raised/95 p-8 shadow-2xl"><p className="text-xs uppercase tracking-[0.25em] text-wine">International advisory archive</p><h1 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink">让每一次咨询，都成为<br />可追溯的教育决策档案。</h1><p className="mt-4 text-sm leading-6 text-muted-foreground">客户研判、学生服务、运营协同与智能报告，在同一安全工作区完成。</p></div>
    </section>
    <section className="flex items-center justify-center px-5 py-10 sm:px-10">
      <div className="w-full max-w-md">
        <div className="mb-10 border-l-4 border-wine pl-5"><p className="font-serif text-3xl font-semibold text-ink">粹教智服</p><p className="mt-1 text-xs uppercase tracking-[0.22em] text-wine">Access portal · secure identity</p></div>
        <div className="border border-bronze/45 bg-paper-raised p-6 shadow-[0_20px_50px_rgb(52_40_24/10%)] sm:p-8"><h2 className="font-serif text-2xl font-semibold">登录工作区</h2><p className="mt-2 text-sm text-muted-foreground">使用已授权的组织账号继续。</p>
          {error && <Alert variant="destructive" className="mt-5" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5" noValidate><div><Label htmlFor="username">用户名</Label><Input id="username" autoComplete="username" spellCheck={false} disabled={isSubmitting} aria-invalid={Boolean(errors.username)} {...register('username')} />{errors.username && <p className="mt-1 text-xs text-destructive">{errors.username.message}</p>}</div><div><Label htmlFor="password">密码</Label><div className="relative"><Input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" disabled={isSubmitting} aria-invalid={Boolean(errors.password)} className="pr-11" {...register('password')} /><button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={showPassword ? '隐藏密码' : '显示密码'}>{showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}</button></div>{errors.password && <p className="mt-1 text-xs text-destructive">{errors.password.message}</p>}</div><Button type="submit" className="h-11 w-full" disabled={isSubmitting}>{isSubmitting ? <span aria-live="polite">正在验证…</span> : <><LogIn aria-hidden />登录</>}</Button></form>
          <p className="mt-6 flex items-center gap-2 border-t border-bronze/25 pt-5 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4 text-wine" />访问令牌仅保存在当前浏览器，不会向第三方服务暴露内部密钥。</p>
        </div>
      </div>
    </section>
  </main>
}
