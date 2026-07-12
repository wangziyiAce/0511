/** 响应式应用壳：桌面固定档案导航，移动端使用可关闭抽屉。 */
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopHeader from './TopHeader'

export default function AppShell() {
  const [navigationOpen, setNavigationOpen] = useState(false)
  return <div className="min-h-screen bg-paper text-ink">
    <a href="#main-content" className="fixed left-3 top-3 z-[60] -translate-y-20 bg-wine px-4 py-2 text-sm text-white transition-transform focus:translate-y-0">跳到主要内容</a>
    <Sidebar open={navigationOpen} onClose={() => setNavigationOpen(false)} />
    {navigationOpen && <button aria-label="关闭导航遮罩" className="fixed inset-0 z-30 bg-black/45 lg:hidden" onClick={() => setNavigationOpen(false)} />}
    <div className="min-h-screen lg:pl-64">
      <TopHeader onMenu={() => setNavigationOpen(true)} />
      <main id="main-content" tabIndex={-1} className="page-enter mx-auto w-full max-w-[1600px] px-4 py-5 focus:outline-none sm:px-6 lg:px-8 lg:py-8"><Outlet /></main>
    </div>
  </div>
}
