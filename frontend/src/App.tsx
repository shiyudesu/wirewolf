import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import LeaderboardPage from './pages/LeaderboardPage'
import GamesPage from './pages/GamesPage'
import GameReplayPage from './pages/GameReplayPage'
import EvolutionPage from './pages/EvolutionPage'
import WatchPage from './pages/WatchPage'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/games" element={<GamesPage />} />
        <Route path="/games/:gameId" element={<GameReplayPage />} />
        <Route path="/evolution" element={<EvolutionPage />} />
        <Route path="/watch" element={<WatchPage />} />
      </Routes>
    </Layout>
  )
}

export default App
