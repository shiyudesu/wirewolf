import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

interface EvolutionPoint {
  strategy_version: number
  win_rate: number
  score: number
  role?: string
  model_name?: string
  games?: number
}

export default function EvolutionPage() {
  const [data, setData] = useState<Record<number, EvolutionPoint[]>>({})
  const [selectedAgent, setSelectedAgent] = useState<number>(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 先从 leaderboard 获取有数据的所有 agent_id
    fetch(`${API_BASE}/api/leaderboard?limit=100`)
      .then((r) => r.json())
      .then((leaderboard) => {
        // leaderboard 按 role+version 聚合，无法直接得到 agent_id
        // 退而尝试查询 agent 1-12
        const agentIds = Array.from({ length: 12 }, (_, i) => i + 1)
        return Promise.all(
          agentIds.map((id) =>
            fetch(`${API_BASE}/api/evolution/${id}`)
              .then((r) => r.json())
              .then((d) => ({ id, data: d }))
          )
        )
      })
      .then((results) => {
        const map: Record<number, EvolutionPoint[]> = {}
        results.forEach((r) => {
          if (r.data.length > 0) map[r.id] = r.data
        })
        setData(map)
        setLoading(false)
      })
  }, [])

  const chartData = (data[selectedAgent] || []).map((d) => ({
    version: `v${d.strategy_version}`,
    胜率: d.win_rate ? d.win_rate * 100 : 0,
    评分: d.score ? d.score : 0,
  }))

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-text">进化追踪</h2>

      {/* Agent Selector */}
      <div className="flex gap-2">
        {Object.keys(data).map((id) => (
          <button
            key={id}
            onClick={() => setSelectedAgent(Number(id))}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              selectedAgent === Number(id)
                ? 'bg-primary text-white'
                : 'bg-bg-card text-text-muted hover:text-text border border-border'
            }`}
          >
            Agent {id}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : chartData.length === 0 ? (
        <div className="text-center py-12 text-text-muted">
          暂无进化数据，请先运行批量对局或进化循环
        </div>
      ) : (
        <div className="space-y-6">
          {/* Chart */}
          <div className="p-4 rounded-xl bg-bg-card border border-border">
            <h3 className="text-sm font-medium text-text-muted mb-4">
              Agent {selectedAgent} 策略演进
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="version" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    color: '#e2e8f0',
                  }}
                />
                <Legend />
                <Line type="monotone" dataKey="胜率" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="评分" stroke="#6366f1" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Version Table */}
          <div className="p-4 rounded-xl bg-bg-card border border-border">
            <h3 className="text-sm font-medium text-text-muted mb-3">版本详情</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted">
                  <th className="text-left px-3 py-2">版本</th>
                  <th className="text-left px-3 py-2">角色</th>
                  <th className="text-left px-3 py-2">模型</th>
                  <th className="text-left px-3 py-2">局数</th>
                  <th className="text-left px-3 py-2">胜率</th>
                  <th className="text-left px-3 py-2">评分</th>
                </tr>
              </thead>
              <tbody>
                {data[selectedAgent]?.map((d, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="px-3 py-2 text-text">v{d.strategy_version}</td>
                    <td className="px-3 py-2 text-text">{d.role || '-'}</td>
                    <td className="px-3 py-2 text-text">{d.model_name || '-'}</td>
                    <td className="px-3 py-2 text-text">{d.games || 0}</td>
                    <td className="px-3 py-2 text-text">
                      {d.win_rate ? (d.win_rate * 100).toFixed(1) : 0}%
                    </td>
                    <td className="px-3 py-2 text-text">
                      {d.score ? d.score.toFixed(1) : 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
