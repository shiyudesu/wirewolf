import { Play, Trophy, Dna } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Test() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Link to="/games" className="group p-6 rounded-xl bg-bg-card border border-border">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
            <Play className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-text">观战对局</h3>
        </div>
      </Link>
      <Link to="/leaderboard" className="group p-6 rounded-xl bg-bg-card border border-border">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
            <Trophy className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-text">排行榜</h3>
        </div>
      </Link>
      <Link to="/evolution" className="group p-6 rounded-xl bg-bg-card border border-border">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
            <Dna className="w-5 h-5" />
          </div>
          <h3 className="font-semibold text-text">进化追踪</h3>
        </div>
      </Link>
    </div>
  )
}
