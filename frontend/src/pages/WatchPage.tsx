import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Wifi, WifiOff, Users, MessageSquare, Skull, Moon, Sun, Send } from 'lucide-react'

interface WatchEvent {
  type: string
  [key: string]: any
}

const WS_BASE = import.meta.env.VITE_WS_BASE || 'ws://localhost:8000'
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const roleColors: Record<string, string> = {
  werewolf: 'text-werewolf border-werewolf/30 bg-werewolf/10',
  seer: 'text-seer border-seer/30 bg-seer/10',
  witch: 'text-witch border-witch/30 bg-witch/10',
  hunter: 'text-hunter border-hunter/30 bg-hunter/10',
  villager: 'text-villager border-villager/30 bg-villager/10',
}

const roleNames: Record<string, string> = {
  werewolf: '狼人', seer: '预言家', witch: '女巫', hunter: '猎人', villager: '平民',
}

export default function WatchPage() {
  const [searchParams] = useSearchParams()
  const gameId = searchParams.get('game') || ''

  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<WatchEvent[]>([])
  const [players, setPlayers] = useState<any[]>([])
  const [alivePlayers, setAlivePlayers] = useState<number[]>([])
  const [phase, setPhase] = useState('')
  const [roundNum, setRoundNum] = useState(0)
  const [winner, setWinner] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Human player state
  const [humanTurn, setHumanTurn] = useState<any>(null)
  const [humanSeats, setHumanSeats] = useState<number[]>([])
  const [mySeat, setMySeat] = useState<number | null>(null)
  const [myRole, setMyRole] = useState<string | null>(null)

  useEffect(() => {
    if (!gameId) return

    const ws = new WebSocket(`${WS_BASE}/ws/watch/${gameId}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (e) => {
      const data: WatchEvent = JSON.parse(e.data)
      setEvents((prev) => [...prev, data])

      switch (data.type) {
        case 'game_start':
          // spectators 收到的是脱敏版本（不含 role）
          // human 玩家会额外收到 my_role
          const incomingPlayers = data.players || []
          setPlayers(
            incomingPlayers.map((p: any) => ({
              ...p,
              role: p.role || 'unknown',
            }))
          )
          setAlivePlayers(incomingPlayers?.map((p: any) => p.player_id) || [])
          setHumanSeats(data.human_seats || [])
          // 如果后端私发了 my_role，记录下来
          if (data.my_role) {
            setMyRole(data.my_role)
          }
          break
        case 'phase_change':
          setPhase(data.phase)
          setRoundNum(data.round_num)
          setAlivePlayers(data.alive_players || [])
          setHumanTurn(null)
          break
        case 'public_chat':
          // handled via events
          break
        case 'death_announce':
          setAlivePlayers((prev) => prev.filter((id) => id !== data.player_id))
          break
        case 'human_turn':
          if (mySeat === data.agent_id) {
            setHumanTurn(data)
          }
          break
        case 'game_over':
          setWinner(data.winner)
          setAlivePlayers(data.players?.filter((p: any) => p.alive).map((p: any) => p.player_id) || [])
          setHumanTurn(null)
          break
      }
    }

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      clearInterval(ping)
      ws.close()
    }
  }, [gameId, mySeat])

  const submitAction = async (actionType: string, targetId?: number, content?: string) => {
    if (!gameId || !mySeat) return
    await fetch(`${API_BASE}/api/game/${gameId}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: mySeat,
        action_type: actionType,
        target_id: targetId,
        content: content,
      }),
    })
    setHumanTurn(null)
  }

  const getPhaseIcon = () => {
    if (phase.includes('night')) return <Moon className="w-4 h-4" />
    if (phase.includes('day')) return <Sun className="w-4 h-4" />
    return null
  }

  const getPhaseName = () => {
    const names: Record<string, string> = {
      night_werewolf: '狼人行动',
      night_seer: '预言家查验',
      night_witch: '女巫行动',
      day_announce: '公布死亡',
      day_discuss: '白天发言',
      day_vote: '投票',
      day_execution: '执行放逐',
      game_over: '游戏结束',
    }
    return names[phase] || phase
  }

  if (!gameId) {
    return (
      <div className="text-center py-12 text-text-muted">
        请在 URL 中传入 ?game=xxx 参数来观战对局
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Status Bar */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-bg-card border border-border">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-text">{gameId.slice(0, 8)}</span>
          {connected ? (
            <span className="flex items-center gap-1 text-xs text-good">
              <Wifi className="w-3 h-3" /> 已连接
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-werewolf">
              <WifiOff className="w-3 h-3" /> 未连接
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm">
          {phase && (
            <span className="flex items-center gap-1.5 text-text">
              {getPhaseIcon()}
              第{roundNum}轮 · {getPhaseName()}
            </span>
          )}
          {winner && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              winner === 'werewolf' ? 'bg-werewolf/15 text-werewolf' : 'bg-good/15 text-good'
            }`}>
              {winner === 'werewolf' ? '狼人胜利' : '好人胜利'}
            </span>
          )}
        </div>
      </div>

      {/* Seat selector for human players */}
      {humanSeats.length > 0 && !mySeat && (
        <div className="p-4 rounded-xl bg-bg-card border border-border">
          <p className="text-sm text-text mb-2">选择你的座位:</p>
          <div className="flex gap-2 flex-wrap">
            {humanSeats.map((seat) => (
              <button
                key={seat}
                onClick={() => setMySeat(seat)}
                className="px-3 py-1.5 rounded-md bg-primary/15 text-primary text-sm font-medium hover:bg-primary/25 transition-colors"
              >
                {seat}号
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Human action panel */}
      {humanTurn && mySeat === humanTurn.agent_id && (
        <HumanActionPanel turn={humanTurn} onSubmit={submitAction} alivePlayers={alivePlayers} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Players */}
        <div className="lg:col-span-1 space-y-3">
          <h3 className="text-sm font-medium text-text-muted flex items-center gap-1.5">
            <Users className="w-4 h-4" /> 玩家状态
            {mySeat && (
              <span className="ml-2 text-xs text-primary">你是 {mySeat}号</span>
            )}
          </h3>
          <div className="grid grid-cols-3 gap-2">
            {players.map((p) => {
              const isAlive = alivePlayers.includes(p.player_id)
              const isMe = mySeat === p.player_id
              // 信息隔离：spectator / 其他 human 看不到角色
              const showRole = isMe && myRole ? myRole : p.role
              const isKnown = isMe || (showRole && showRole !== 'unknown')
              return (
                <div
                  key={p.player_id}
                  className={`p-2 rounded-lg border text-center text-xs ${
                    isAlive
                      ? (isKnown ? (roleColors[showRole] || 'border-border bg-bg-card text-text') : 'border-border bg-bg-card/50 text-text-muted')
                      : 'border-border/30 bg-bg-card/50 text-text-muted opacity-50 line-through'
                  } ${isMe ? 'ring-2 ring-primary' : ''}`}
                >
                  <div className="font-bold text-sm">{p.player_id}号</div>
                  <div className="mt-0.5">{isKnown ? (roleNames[showRole] || showRole) : '???'}</div>
                  {humanSeats.includes(p.player_id) && (
                    <div className="text-[10px] text-primary mt-0.5">👤玩家</div>
                  )}
                  {!isAlive && (
                    <div className="flex items-center justify-center gap-1 mt-1 text-xs text-werewolf">
                      <Skull className="w-3 h-3" />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: Event Feed */}
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-medium text-text-muted flex items-center gap-1.5">
            <MessageSquare className="w-4 h-4" /> 实时事件
          </h3>
          <div className="h-96 overflow-y-auto space-y-2 p-3 rounded-lg bg-bg-card border border-border">
            {events.length === 0 && (
              <div className="text-center text-text-muted text-sm py-8">等待对局开始...</div>
            )}
            {events.map((ev, i) => (
              <EventItem key={i} event={ev} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function HumanActionPanel({
  turn,
  onSubmit,
  alivePlayers,
}: {
  turn: any
  onSubmit: (type: string, target?: number, content?: string) => void
  alivePlayers: number[]
}) {
  const [content, setContent] = useState('')
  const [target, setTarget] = useState<number | undefined>(undefined)

  const availableActions = turn.available_actions || []
  const isSpeak = turn.phase?.includes('discuss')
  const isVote = turn.phase?.includes('vote')
  const isNight = turn.phase?.includes('night')

  return (
    <div className="p-4 rounded-xl bg-primary/10 border border-primary/30">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-primary">
          轮到你了！{turn.agent_id}号 ({roleNames[turn.role] || turn.role})
        </h3>
        <span className="text-xs text-text-muted">{turn.phase}</span>
      </div>

      {/* Private info */}
      {turn.observation?.private_info && (
        <div className="mb-3 p-2 rounded bg-bg-card border border-border text-xs text-text">
          <span className="text-text-muted">私有信息:</span> {turn.observation.private_info}
        </div>
      )}

      {/* Target selection for non-speak actions */}
      {(isNight || isVote) && availableActions.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-text-muted mb-1">选择目标:</p>
          <div className="flex gap-2 flex-wrap">
            {alivePlayers
              .filter((id) => id !== turn.agent_id)
              .map((id) => (
                <button
                  key={id}
                  onClick={() => setTarget(id)}
                  className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                    target === id
                      ? 'bg-primary text-white'
                      : 'bg-bg-card border border-border text-text-muted hover:text-text'
                  }`}
                >
                  {id}号
                </button>
              ))}
            <button
              onClick={() => setTarget(undefined)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                target === undefined
                  ? 'bg-primary text-white'
                  : 'bg-bg-card border border-border text-text-muted hover:text-text'
              }`}
            >
              无目标
            </button>
          </div>
        </div>
      )}

      {/* Speak content */}
      {isSpeak && (
        <div className="mb-3">
          <p className="text-xs text-text-muted mb-1">发言内容:</p>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="输入你的发言..."
            className="w-full p-2 rounded bg-bg-card border border-border text-sm text-text placeholder:text-text-muted resize-none"
            rows={2}
          />
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 flex-wrap">
        {availableActions.map((action: string) => (
          <button
            key={action}
            onClick={() => onSubmit(action, target, content || undefined)}
            disabled={isSpeak && !content.trim() && action === 'speak'}
            className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
          >
            <Send className="w-3 h-3" />
            {action === 'kill' && '刀人'}
            {action === 'check' && '查验'}
            {action === 'save' && '救人'}
            {action === 'poison' && '毒人'}
            {action === 'shoot' && '开枪'}
            {action === 'speak' && '发言'}
            {action === 'vote' && '投票'}
            {action === 'pass' && '跳过'}
            {!['kill', 'check', 'save', 'poison', 'shoot', 'speak', 'vote', 'pass'].includes(action) && action}
          </button>
        ))}
      </div>
    </div>
  )
}

function EventItem({ event }: { event: WatchEvent }) {
  switch (event.type) {
    case 'game_start':
      return (
        <div className="text-sm text-primary font-medium">
          🎮 游戏开始！{event.players?.length}人局
          {event.human_seats?.length > 0 && (
            <span className="ml-2 text-text-muted">
              人类玩家: {event.human_seats.join(',')}号
            </span>
          )}
        </div>
      )
    case 'phase_change':
      return (
        <div className="text-sm text-text-muted">
          <span className="text-primary font-medium">➤ 第{event.round_num}轮</span>
          {' '}{event.phase}
        </div>
      )
    case 'public_chat':
      return (
        <div className="text-sm">
          <span className="text-text-muted">{event.speaker_id}号</span>
          <span className="text-text-muted text-xs ml-1">({roleNames[event.role] || event.role})</span>
          <span className="text-text ml-2">{event.content}</span>
        </div>
      )
    case 'vote_update':
      return (
        <div className="text-sm text-text-muted">
          🗳️ 投票:
          {Object.entries(event.votes || {}).map(([voter, target]) => (
            <span key={voter} className="ml-2">{voter}→{String(target)}</span>
          ))}
          {event.executed && (
            <span className="text-werewolf ml-2">| {event.executed}号被放逐</span>
          )}
        </div>
      )
    case 'death_announce':
      return (
        <div className="text-sm text-werewolf flex items-center gap-1">
          <Skull className="w-3 h-3" />
          {event.player_id}号 死亡 ({event.reason === 'night' ? '夜间' : '投票'})
        </div>
      )
    case 'human_turn':
      return (
        <div className="text-sm text-primary">
          👤 等待 {event.agent_id}号人类玩家操作...
        </div>
      )
    case 'game_over':
      return (
        <div className={`text-sm font-bold ${
          event.winner === 'werewolf' ? 'text-werewolf' : 'text-good'
        }`}>
          🏆 游戏结束！{event.winner === 'werewolf' ? '狼人' : '好人'}胜利
          （共{event.total_rounds}轮）
        </div>
      )
    default:
      return (
        <div className="text-xs text-text-muted font-mono">
          {JSON.stringify(event)}
        </div>
      )
  }
}
