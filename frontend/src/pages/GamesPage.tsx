import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Clock, ChevronRight } from 'lucide-react'

interface Game {
  game_id: string
  winner: string
  total_rounds: number
  played_at: string
  config: string
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function GamesPage() {
  const [games, setGames] = useState<Game[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/games?limit=50`)
      .then((r) => r.json())
      .then((d) => {
        setGames(d)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const parseConfig = (cfg: string) => {
    try {
      return JSON.parse(cfg)
    } catch {
      return {}
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-text">对局列表</h2>

      {loading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : games.length === 0 ? (
        <div className="text-center py-12 text-text-muted">暂无对局数据</div>
      ) : (
        <div className="grid gap-3">
          {games.map((game) => {
            const cfg = parseConfig(game.config)
            return (
              <Link
                key={game.game_id}
                to={`/games/${game.game_id}`}
                className="flex items-center gap-4 p-4 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors group"
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold ${
                  game.winner === 'werewolf'
                    ? 'bg-werewolf/15 text-werewolf'
                    : 'bg-good/15 text-good'
                }`}>
                  {game.winner === 'werewolf' ? '狼' : '好'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text-muted">{game.game_id.slice(0, 8)}</span>
                    <span className="text-sm text-text-muted">
                      {cfg.player_count}人局 · {cfg.werewolf_count}狼
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-text-muted">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {game.total_rounds}轮
                    </span>
                    <span>{new Date(game.played_at).toLocaleString('zh-CN')}</span>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-text-muted group-hover:text-primary transition-colors" />
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
