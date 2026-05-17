import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Skull } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const roleColors: Record<string, string> = {
  werewolf: 'bg-werewolf/20 text-werewolf border-werewolf/30',
  seer: 'bg-seer/20 text-seer border-seer/30',
  witch: 'bg-witch/20 text-witch border-witch/30',
  hunter: 'bg-hunter/20 text-hunter border-hunter/30',
  villager: 'bg-villager/20 text-villager border-villager/30',
}

const roleNames: Record<string, string> = {
  werewolf: '狼人', seer: '预言家', witch: '女巫', hunter: '猎人', villager: '平民',
}

export default function GameReplayPage() {
  const { gameId } = useParams<{ gameId: string }>()
  const [game, setGame] = useState<any>(null)
  const [report, setReport] = useState<any>(null)
  const [metrics, setMetrics] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'rounds' | 'report'>('overview')

  useEffect(() => {
    if (!gameId) return
    Promise.all([
      fetch(`${API_BASE}/api/games/${gameId}`).then((r) => r.json()),
      fetch(`${API_BASE}/api/games/${gameId}/report`).then((r) => r.json().catch(() => null)),
      fetch(`${API_BASE}/api/games/${gameId}/metrics`).then((r) => r.json().catch(() => null)),
    ]).then(([g, r, m]) => {
      setGame(g)
      setReport(r)
      setMetrics(m)
      setLoading(false)
    })
  }, [gameId])

  if (loading) return <div className="text-center py-12 text-text-muted">加载中...</div>
  if (!game) return <div className="text-center py-12 text-text-muted">对局不存在</div>

  const players = game.meta?.players || []
  const rounds = game.rounds || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/games" className="text-text-muted hover:text-text transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h2 className="text-xl font-bold text-text">对局 {gameId?.slice(0, 8)}</h2>
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
          game.meta?.winner === 'werewolf'
            ? 'bg-werewolf/15 text-werewolf'
            : 'bg-good/15 text-good'
        }`}>
          {game.meta?.winner === 'werewolf' ? '狼人胜利' : '好人胜利'}
        </span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-bg-card rounded-lg border border-border w-fit">
        {(['overview', 'rounds', 'report'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-primary/15 text-primary'
                : 'text-text-muted hover:text-text'
            }`}
          >
            {tab === 'overview' ? '概览' : tab === 'rounds' ? '逐轮' : '复盘'}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Players */}
          <div>
            <h3 className="text-sm font-medium text-text-muted mb-3">玩家配置</h3>
            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {players.map((p: any) => (
                <div
                  key={p.player_id}
                  className={`p-3 rounded-lg border text-center ${
                    p.alive
                      ? roleColors[p.role] || 'bg-bg-card text-text border-border'
                      : 'bg-bg-card/50 text-text-muted border-border/50 opacity-60'
                  }`}
                >
                  <div className="text-lg font-bold">{p.player_id}号</div>
                  <div className="text-xs mt-1">{roleNames[p.role] || p.role}</div>
                  {!p.alive && (
                    <div className="flex items-center justify-center gap-1 mt-1 text-xs text-werewolf">
                      <Skull className="w-3 h-3" />
                      已死亡
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Metrics */}
          {metrics && (
            <div>
              <h3 className="text-sm font-medium text-text-muted mb-3">评测指标</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {Object.entries(metrics.outcome || {}).map(([pid, m]: [string, any]) => (
                  <div key={pid} className="p-3 rounded-lg bg-bg-card border border-border text-sm">
                    <div className="font-medium text-text">{pid}号</div>
                    <div className="text-text-muted text-xs">{roleNames[m.role] || m.role}</div>
                    <div className="mt-2 space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-text-muted">胜率</span>
                        <span className="text-text">{(m.win_rate * 100).toFixed(0)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">存活</span>
                        <span className="text-text">{m.survival_rounds.toFixed(1)}轮</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Rounds */}
      {activeTab === 'rounds' && (
        <div className="space-y-4">
          {rounds.map((round: any, idx: number) => (
            <div key={idx} className="p-4 rounded-xl bg-bg-card border border-border">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-bold text-primary">第 {round.round_num} 轮</span>
                <span className="text-xs text-text-muted">{round.phase}</span>
              </div>
              <div className="space-y-2">
                {round.actions?.map((action: any, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-text-muted font-mono w-6">{action.agent_id}号</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      action.action_type === 'kill' ? 'bg-werewolf/15 text-werewolf' :
                      action.action_type === 'check' ? 'bg-seer/15 text-seer' :
                      action.action_type === 'save' ? 'bg-witch/15 text-witch' :
                      action.action_type === 'poison' ? 'bg-werewolf/15 text-werewolf' :
                      action.action_type === 'speak' ? 'bg-villager/15 text-villager' :
                      action.action_type === 'vote' ? 'bg-hunter/15 text-hunter' :
                      'bg-border text-text-muted'
                    }`}>
                      {action.action_type}
                    </span>
                    {action.target_id && (
                      <span className="text-text-muted">→ {action.target_id}号</span>
                    )}
                    {action.content && (
                      <span className="text-text truncate">{action.content}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Report */}
      {activeTab === 'report' && report && (
        <div className="space-y-6">
          <div className="p-4 rounded-xl bg-bg-card border border-border">
            <h3 className="font-medium text-text mb-2">玩家评分</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Object.entries(report.player_scores || {}).map(([pid, score]: [string, any]) => (
                <div key={pid} className="flex items-center gap-2">
                  <span className="text-text-muted text-sm">{pid}号</span>
                  <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${Math.min(score, 100)}%` }}
                    />
                  </div>
                  <span className="text-sm text-text">{score.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </div>

          {report.pivotal_moments?.length > 0 && (
            <div className="p-4 rounded-xl bg-bg-card border border-border">
              <h3 className="font-medium text-text mb-2">关键时刻</h3>
              <div className="space-y-2">
                {report.pivotal_moments.map((m: any, i: number) => (
                  <div key={i} className="text-sm">
                    <span className="text-primary">第{m.round}轮</span>
                    <span className="text-text ml-2">{m.event}</span>
                    <span className="text-text-muted ml-2">{m.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.timeline && (
            <div className="p-4 rounded-xl bg-bg-card border border-border">
              <h3 className="font-medium text-text mb-2">决策时间线</h3>
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {report.timeline.slice(0, 30).map((t: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-text-muted w-12">R{t.round}</span>
                    <span className="text-text-muted w-20">{t.phase}</span>
                    <span className="text-text">{t.agent_id}号</span>
                    <span className={`px-1 rounded ${
                      t.action === 'kill' ? 'bg-werewolf/15 text-werewolf' :
                      t.action === 'vote' ? 'bg-hunter/15 text-hunter' :
                      'bg-border text-text-muted'
                    }`}>{t.action}</span>
                    {t.target && <span className="text-text-muted">→ {t.target}号</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
