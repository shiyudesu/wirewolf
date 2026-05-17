"""批量对局运行器."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.llm.client import LLMClient
from app.llm.mock_client import MockLLMClient
from app.models.game import GameConfig
from app.engine.game_master import GameMaster
from app.evaluation.leaderboard import LeaderboardDB
from app.evaluation.metrics import MetricsCalculator
from app.evaluation.report import ReportGenerator


class BatchRunner:
    """批量运行多局游戏并自动评测."""

    def __init__(
        self,
        config: GameConfig,
        games: int = 10,
        use_mock: bool = False,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.config = config
        self.games = games
        self.use_mock = use_mock
        self.llm = llm_client or (MockLLMClient() if use_mock else LLMClient())
        self.db = LeaderboardDB()
        self.results: list[dict] = []

    async def run(self) -> dict:
        """运行批量对局，返回统计摘要."""
        print(f"\n{'='*50}")
        print(f"开始批量对局: {self.games} 局")
        print(f"配置: {self.config.model_dump()}")
        print(f"{'='*50}\n")

        start_time = datetime.utcnow()

        for i in range(self.games):
            print(f"\n--- 第 {i+1}/{self.games} 局 ---")
            gm = GameMaster(config=self.config, llm_client=self.llm)
            winner = await gm.run()

            # 记录到数据库
            await self.db.record_game(
                game_id=gm.game_id,
                config=self.config.model_dump(),
                winner=winner.value if winner else None,
                total_rounds=gm.game_state.round_num,
            )

            # 计算指标并入库
            calculator = MetricsCalculator(gm.log_file)
            outcome_metrics = calculator.compute_outcome_metrics()
            process_metrics = calculator.compute_process_metrics()

            report_gen = ReportGenerator(gm.log_file)
            report = report_gen.generate()

            for pid, om in outcome_metrics.items():
                pm = process_metrics.get(pid)
                score = report.player_scores.get(pid, 0.0)
                agent = gm.agents.get(pid)
                version = agent.profile.version if agent else 1

                await self.db.record_player_stats(
                    game_id=gm.game_id,
                    outcome=om,
                    process=pm,
                    overall_score=score,
                    strategy_version=version,
                )

            self.results.append({
                "game_id": gm.game_id,
                "winner": winner.value if winner else None,
                "rounds": gm.game_state.round_num,
            })

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # 统计摘要
        werewolf_wins = sum(1 for r in self.results if r["winner"] == "werewolf")
        good_wins = sum(1 for r in self.results if r["winner"] == "good")
        avg_rounds = sum(r["rounds"] for r in self.results) / max(len(self.results), 1)

        summary = {
            "total_games": self.games,
            "werewolf_wins": werewolf_wins,
            "good_wins": good_wins,
            "avg_rounds": round(avg_rounds, 2),
            "duration_sec": round(duration, 2),
            "games_per_sec": round(self.games / max(duration, 0.001), 2),
        }

        print(f"\n{'='*50}")
        print("批量对局完成!")
        print(f"  狼人胜: {werewolf_wins} | 好人胜: {good_wins}")
        print(f"  平均轮数: {avg_rounds:.1f}")
        print(f"  耗时: {duration:.1f}s")
        print(f"{'='*50}")

        return summary
