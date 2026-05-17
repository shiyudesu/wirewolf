import { Link, useLocation } from 'react-router-dom'
import { Trophy, Home, List, Dna, Swords } from 'lucide-react'

const navItems = [
  { path: '/', label: '大厅', icon: Home },
  { path: '/games', label: '对局', icon: List },
  { path: '/leaderboard', label: '排行榜', icon: Trophy },
  { path: '/evolution', label: '进化', icon: Dna },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-border bg-bg-card/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-primary font-bold text-lg">
            <Swords className="w-5 h-5" />
            WireWolf
          </Link>
          <nav className="flex gap-1">
            {navItems.map((item) => {
              const active = location.pathname === item.path
              const Icon = item.icon
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? 'bg-primary/15 text-primary'
                      : 'text-text-muted hover:text-text hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-4 text-center text-text-muted text-sm">
        WireWolf — 狼人杀多 Agent 自进化平台
      </footer>
    </div>
  )
}
