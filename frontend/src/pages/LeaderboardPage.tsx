import { useEffect, useState } from 'react'
import { Trophy } from 'lucide-react'

interface LeaderboardRow {
  role: string
  strategy_version: number
  model_name: string
  games: number
  avg_win_rate: number
  avg_score: number
  avg_survival: number
  avg_info_utilization: number
  avg_defense_quality: number
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const roleColors: Record<string, string> = {
  werewolf: 'text-werewolf',
  seer: 'text-seer',
  witch: 'text-witch',
  hunter: 'text-hunter',
  villager: 'text-villager',
}

const roleNames: Record<string, string> = {
  werewolf: '狼人',
  seer: '预言家',
  witch: '女巫',
  hunter: '猎人',
  villager: '平民',
}

export default function LeaderboardPage() {
  const [data, setData] = useState<LeaderboardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('')
  const [modelFilter, setModelFilter] = useState<string>('')

  useEffect(() => {
    const params = new URLSearchParams()
    if (filter) params.set('role', filter)
    if (modelFilter) params.set('model_name', modelFilter)
    fetch(`${API_BASE}/api/leaderboard?${params.toString()}`)
      .then((r) => r.json())
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [filter, modelFilter])

  // 从数据中提取所有 model_name
  const allModels = Array.from(new Set(data.map((r) => r.model_name).filter(Boolean)))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-text flex items-center gap-2">
          <Trophy className="w-5 h-5 text-primary" />
          排行榜
        </h2>
        <div className="flex gap-2 flex-wrap">
          {['', 'werewolf', 'seer', 'witch', 'hunter', 'villager'].map((r) => (
            <button
              key={r || 'all'}
              onClick={() => setFilter(r)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                filter === r
                  ? 'bg-primary text-white'
                  : 'bg-bg-card text-text-muted hover:text-text border border-border'
              }`}
            >
              {r ? roleNames[r] : '全部'}
            </button>
          ))}
          {allModels.length > 0 && (
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="px-2 py-1 rounded-md bg-bg-card border border-border text-xs text-text-muted"
            >
              <option value="">所有模型</option>
              {allModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : data.length === 0 ? (
        <div className="text-center py-12 text-text-muted">暂无数据</div>
      ) : (
        <div className="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-text-muted">
                <th className="text-left px-4 py-3 font-medium">排名</th>
                <th className="text-left px-4 py-3 font-medium">角色</th>
                <th className="text-left px-4 py-3 font-medium">版本</th>
                <th className="text-left px-4 py-3 font-medium">模型</th>
                <th className="text-left px-4 py-3 font-medium">局数</th>
                <th className="text-left px-4 py-3 font-medium">胜率</th>
                <th className="text-left px-4 py-3 font-medium">均分</th>
                <th className="text-left px-4 py-3 font-medium">存活</th>
                <th className="text-left px-4 py-3 font-medium">信息利用</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr
                  key={`${row.role}-${row.strategy_version}`}
                  className="border-b border-border/50 hover:bg-white/[0.02] transition-colors"
                >
                  <td className="px-4 py-3">
                    {i < 3 ? (
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                        i === 0 ? 'bg-yellow-500/20 text-yellow-400' :
                        i === 1 ? 'bg-gray-400/20 text-gray-300' :
                        'bg-amber-700/20 text-amber-500'
                      }`}>
                        {i + 1}
                      </span>
                    ) : (
                      <span className="text-text-muted pl-1.5">{i + 1}</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 font-medium ${roleColors[row.role] || 'text-text'}`}>
                    {roleNames[row.role] || row.role}
                  </td>
                  <td className="px-4 py-3 text-text-muted">v{row.strategy_version}</td>
                  <td className="px-4 py-3 text-text-muted">{row.model_name || '-'}</td>
                  <td className="px-4 py-3 text-text-muted">{row.games}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-border rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full"
                          style={{ width: `${(row.avg_win_rate * 100).toFixed(0)}%` }}
                        />
                      </div>
                      <span className="text-text">{(row.avg_win_rate * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-text">{row.avg_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-text-muted">{row.avg_survival.toFixed(1)}轮</td>
                  <td className="px-4 py-3 text-text-muted">{(row.avg_info_utilization * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
