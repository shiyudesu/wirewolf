#!/usr/bin/env python3
"""命令行运行一局狼人杀对局（MVP测试脚本）."""

from __future__ import annotations

import asyncio
import argparse
import os
import sys

# 确保 backend 目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.client import LLMClient
from app.models.game import GameConfig
from app.engine.game_master import GameMaster


async def main() -> None:
    parser = argparse.ArgumentParser(description="WireWolf CLI — 运行一局狼人杀")
    parser.add_argument("--players", type=int, default=12, help="玩家总数")
    parser.add_argument("--wolves", type=int, default=4, help="狼人数量")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM 模型")
    parser.add_argument("--reflect", action="store_true", help="结束后触发反思")
    args = parser.parse_args()

    config = GameConfig(
        player_count=args.players,
        werewolf_count=args.wolves,
    )

    llm = LLMClient(model=args.model, temperature=0.5)
    gm = GameMaster(config=config, llm_client=llm)

    winner = await gm.run()

    if args.reflect:
        print("\n--- 局后反思 ---")
        await gm.post_game_reflection()

    print(f"\n游戏结束，获胜阵营: {winner.value if winner else '平局/异常'}")


if __name__ == "__main__":
    asyncio.run(main())
