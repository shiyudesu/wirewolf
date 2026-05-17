#!/usr/bin/env python3
"""评测流水线入口 — 对单个游戏日志进行评测."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.evaluation.metrics import MetricsCalculator
from app.evaluation.report import ReportGenerator
from app.evaluation.leaderboard import LeaderboardDB


async def main() -> None:
    parser = argparse.ArgumentParser(description="WireWolf 评测流水线")
    parser.add_argument("--game-log", type=str, required=True, help="游戏日志 JSONL 文件路径")
    parser.add_argument("--output", type=str, default=None, help="报告输出路径")
    parser.add_argument("--save-to-db", action="store_true", help="是否保存到 Leaderboard 数据库")
    args = parser.parse_args()

    if not os.path.exists(args.game_log):
        print(f"错误: 文件不存在 {args.game_log}")
        sys.exit(1)

    print(f"正在评测: {args.game_log}")

    # 计算指标
    calculator = MetricsCalculator(args.game_log)
    outcome = calculator.compute_outcome_metrics()
    process = calculator.compute_process_metrics()

    print("\n--- 结果指标 ---")
    for pid, m in outcome.items():
        print(f"  {pid}号 ({m.role.value}): 胜率={m.win_rate:.0%}, 存活={m.avg_survival_rounds:.1f}轮")

    # 生成报告
    generator = ReportGenerator(args.game_log)
    report = generator.generate()

    print("\n--- 复盘报告 ---")
    print(f"  游戏ID: {report.game_id}")
    print(f"  获胜方: {report.winner}")
    print(f"  总轮数: {report.total_rounds}")
    print(f"  关键失误:")
    for m in report.key_mistakes:
        print(f"    - {m['player_id']}号({m['role']}): {m['mistake']} [严重度: {m['severity']}]")
    print(f"  玩家评分:")
    for pid, score in report.player_scores.items():
        print(f"    - {pid}号: {score:.1f}分")

    # 保存报告
    if args.output:
        report.save(args.output)
        print(f"\n报告已保存: {args.output}")

    # 保存到数据库
    if args.save_to_db:
        db = LeaderboardDB()
        await db.record_game(
            game_id=report.game_id,
            config=calculator.game_meta.get("config", {}),
            winner=report.winner,
            total_rounds=report.total_rounds,
        )
        for pid, om in outcome.items():
            pm = process.get(pid)
            score = report.player_scores.get(pid, 0.0)
            await db.record_player_stats(
                game_id=report.game_id,
                outcome=om,
                process=pm,
                overall_score=score,
            )
        print("已入库")


if __name__ == "__main__":
    asyncio.run(main())
