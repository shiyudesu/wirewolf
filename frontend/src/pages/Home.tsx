import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Swords, Zap, Activity, Eye, PlusCircle, Play, Trophy, Dna } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function Home() {
  const navigate = useNavigate()
  const [batchStatus, setBatchStatus] = useState<{ total_games: number; werewolf_wins: number; good_wins: number } | null>(null)
  const [running, setRunning] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newGameId, setNewGameId] = useState('')

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)

    // 获取服务端默认模型配置，与 .env 对齐
    fetch(`${API_BASE}/api/config`)
      .then((r) => r.json())
      .then((d) => {
        if (d.llm_model) setModel(d.llm_model)
      })
      .catch(() => {})

    return () => clearInterval(interval)
  }, [])

  const fetchStatus = () => {
    fetch(`${API_BASE}/api/batch/status`)
      .then((r) => r.json())
      .then((d) => setBatchStatus(d))
      .catch(() => {})
  }



  const [humanSeats, setHumanSeats] = useState<number[]>([])
  const [useMock, setUseMock] = useState(true)
  const [model, setModel] = useState('gpt-4o-mini')
  const [playerCount, setPlayerCount] = useState(9)

  const createGame = () => {
    setCreating(true)
    fetch(`${API_BASE}/api/game/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_count: playerCount,
        werewolf_count: playerCount === 9 ? 3 : 4,
        use_mock: useMock,
        model: useMock ? undefined : model,
        human_seats: humanSeats,
      }),
    })
      .then((r) => {
        if (!r.ok) {
          return r.json().then((d) => { throw new Error(d.detail || '创建失败') })
        }
        return r.json()
      })
      .then((d) => {
        setNewGameId(d.game_id)
        setCreating(false)
      })
      .catch((e) => {
        alert(e.message)
        setCreating(false)
      })
  }

  const runBatch = (games: number) => {
    setRunning(true)
    fetch(`${API_BASE}/api/batch/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        games,
        use_mock: useMock,
        model: useMock ? undefined : model,
        player_count: playerCount,
        werewolf_count: playerCount === 9 ? 3 : 4,
      }),
    })
      .then((r) => {
        if (!r.ok) {
          return r.json().then((d) => { throw new Error(d.detail || '启动失败') })
        }
        setTimeout(() => setRunning(false), 1000)
      })
      .catch((e) => {
        alert(e.message)
        setRunning(false)
      })
  }

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="text-center py-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/15 text-primary mb-6">
          <Swords className="w-8 h-8" />
        </div>
        <h1 className="text-4xl font-bold text-text mb-3">WireWolf</h1>
        <p className="text-text-muted text-lg max-w-xl mx-auto">
          狼人杀多 Agent 协作系统 — 让 LLM Agent 自我博弈、自我反思、自我进化
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <button
          onClick={createGame}
          disabled={creating}
          className="group p-5 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors text-left disabled:opacity-50"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <PlusCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-text">创建对局</h3>
              <p className="text-xs text-text-muted">新建一局 {playerCount} 人 Mock 对局</p>
            </div>
          </div>
        </button>

        <button
          onClick={() => runBatch(5)}
          disabled={running}
          className="group p-5 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors text-left disabled:opacity-50"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-text">快速批量</h3>
              <p className="text-xs text-text-muted">运行 5 局</p>
            </div>
          </div>
        </button>

        <button
          onClick={() => runBatch(20)}
          disabled={running}
          className="group p-5 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors text-left disabled:opacity-50"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-text">大规模批量</h3>
              <p className="text-xs text-text-muted">运行 20 局</p>
            </div>
          </div>
        </button>

        <Link
          to="/watch"
          className="group p-5 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-text">实时观战</h3>
              <p className="text-xs text-text-muted">WebSocket 连接观战</p>
            </div>
          </div>
        </Link>
      </div>

      {/* Game settings */}
      <div className="p-4 rounded-xl bg-bg-card border border-border space-y-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-muted">人数:</label>
            <select
              value={playerCount}
              onChange={(e) => {
                const count = Number(e.target.value)
                setPlayerCount(count)
                setHumanSeats(humanSeats.filter((s) => s <= count))
              }}
              className="px-2 py-1 rounded-md bg-bg border border-border text-sm text-text focus:outline-none focus:border-primary"
            >
              <option value={9}>9 人局</option>
              <option value={12}>12 人局</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-muted">模式:</label>
            <button
              onClick={() => setUseMock(!useMock)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                useMock
                  ? 'bg-amber-500/20 text-amber-600 border border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-600 border border-emerald-500/30'
              }`}
            >
              {useMock ? 'Mock 模式' : 'LLM 模式'}
            </button>
          </div>
          {!useMock && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-text-muted">模型:</label>
              <input
                list="model-suggestions"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="输入模型名称"
                className="px-2 py-1 rounded-md bg-bg border border-border text-sm text-text focus:outline-none focus:border-primary w-40"
              />
              <datalist id="model-suggestions">
                <option value="gpt-4o-mini" />
                <option value="gpt-4o" />
                <option value="gpt-3.5-turbo" />
                <option value="deepseek-chat" />
                <option value="qwen-max" />
                <option value="claude-3-5-sonnet" />
              </datalist>
            </div>
          )}
        </div>

        <div>
          <p className="text-sm text-text-muted mb-2">选择人类玩家座位（可选）:</p>
          <div className="flex gap-2 flex-wrap">
            {Array.from({ length: playerCount }, (_, i) => i + 1).map((seat) => (
              <button
                key={seat}
                onClick={() => {
                  if (humanSeats.includes(seat)) {
                    setHumanSeats(humanSeats.filter((s) => s !== seat))
                  } else {
                    setHumanSeats([...humanSeats, seat])
                  }
                }}
                className={`w-8 h-8 rounded-md text-sm font-medium transition-colors ${
                  humanSeats.includes(seat)
                    ? 'bg-primary text-white'
                    : 'bg-bg border border-border text-text-muted hover:text-text'
                }`}
              >
                {seat}
              </button>
            ))}
          </div>
        </div>
      </div>

      {newGameId && (
        <div className="p-4 rounded-xl bg-primary/10 border border-primary/30 text-center">
          <p className="text-sm text-text">对局已创建: <span className="font-mono font-bold">{newGameId}</span></p>
          {humanSeats.length > 0 && (
            <p className="text-xs text-text-muted mt-1">
              人类玩家: {humanSeats.map((s) => s + '号').join(', ')}
            </p>
          )}
          <button
            onClick={() => navigate(`/watch?game=${newGameId}`)}
            className="mt-2 px-4 py-1.5 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-dark transition-colors"
          >
            立即{humanSeats.length > 0 ? '参与' : '观战'}
          </button>
        </div>
      )}

      {/* Feature Cards -->
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link
          to="/games"
          className="group p-6 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Play className="w-5 h-5" />
            </div>
            <h3 className="font-semibold text-text">观战对局</h3>
          </div>
          <p className="text-text-muted text-sm">
            查看历史对局记录，分析每个 Agent 的决策过程与胜负归因
          </p>
        </Link>

        <Link
          to="/leaderboard"
          className="group p-6 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Trophy className="w-5 h-5" />
            </div>
            <h3 className="font-semibold text-text">排行榜</h3>
          </div>
          <p className="text-text-muted text-sm">
            多维度排名：按角色、按模型、按策略版本，量化 Agent 表现
          </p>
        </Link>

        <Link
          to="/evolution"
          className="group p-6 rounded-xl bg-bg-card border border-border hover:border-primary/50 transition-colors"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
              <Dna className="w-5 h-5" />
            </div>
            <h3 className="font-semibold text-text">进化追踪</h3>
          </div>
          <p className="text-text-muted text-sm">
            追踪 Agent 策略从 v1 到 vN 的演变，观察胜率随版本迭代的变化
          </p>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="已完成对局"
          value={batchStatus ? String(batchStatus.total_games) : '--'}
        />
        <StatCard label="Agent 数量" value="12" />
        <StatCard
          label="狼人胜利"
          value={batchStatus ? String(batchStatus.werewolf_wins) : '--'}
        />
        <StatCard
          label="好人胜利"
          value={batchStatus ? String(batchStatus.good_wins) : '--'}
        />
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-4 rounded-lg bg-bg-card border border-border text-center">
      <div className="text-2xl font-bold text-text">{value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
    </div>
  )
}
