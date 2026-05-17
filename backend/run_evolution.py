#!/usr/bin/env python3
"""自进化循环入口脚本."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.game import GameConfig
from app.evolution.loop import EvolutionLoop, EvolutionConfig


async def main() -> None:
    parser = argparse.ArgumentParser(description="WireWolf 自进化循环")
    parser.add_argument("--generations", type=int, default=3, help="进化代数")
    parser.add_argument("--games-per-gen", type=int, default=5, help="每代对局数")
    parser.add_argument("--players", type=int, default=9, help="玩家数")
    parser.add_argument("--wolves", type=int, default=3, help="狼人数")
    parser.add_argument("--mock", action="store_true", help="使用 Mock LLM")
    args = parser.parse_args()

    game_config = GameConfig(
        player_count=args.players,
        werewolf_count=args.wolves,
    )

    evo_config = EvolutionConfig(
        generations=args.generations,
        games_per_generation=args.games_per_gen,
        use_mock=args.mock,
    )

    loop = EvolutionLoop(
        game_config=game_config,
        evo_config=evo_config,
    )

    results = await loop.run()

    print(f"\n{'='*60}")
    print("进化循环全部完成!")
    print(f"{'='*60}")

    accepted = [r for r in results if r.accepted]
    rejected = [r for r in results if not r.accepted]

    print(f"  总优化尝试: {len(results)}")
    print(f"   accepted: {len(accepted)}")
    print(f"   rejected: {len(rejected)}")

    if accepted:
        print("\n--- 成功的进化 ---")
        for r in accepted:
            print(
                f"  Gen{r.generation} Agent{r.agent_id}({r.role}): "
                f"v{r.old_version} -> v{r.new_version} | "
                f"胜率 {r.old_metrics.get('win_rate', 0):.0%} -> {r.new_metrics.get('win_rate', 0):.0%}"
            )


if __name__ == "__main__":
    asyncio.run(main())
