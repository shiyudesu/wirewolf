#!/usr/bin/env python3
"""批量对局入口脚本."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.game import GameConfig
from app.batch.runner import BatchRunner


async def main() -> None:
    parser = argparse.ArgumentParser(description="WireWolf 批量对局")
    parser.add_argument("--games", type=int, default=10, help="对局数量")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--players", type=int, default=9, help="玩家数（无配置文件时）")
    parser.add_argument("--wolves", type=int, default=3, help="狼人数（无配置文件时）")
    parser.add_argument("--mock", action="store_true", help="使用 Mock LLM（无需 API Key）")
    args = parser.parse_args()

    # 加载配置
    if args.config:
        with open(args.config, "r") as f:
            config_data = json.load(f)
        config = GameConfig(**config_data)
    else:
        config = GameConfig(
            player_count=args.players,
            werewolf_count=args.wolves,
        )

    runner = BatchRunner(
        config=config,
        games=args.games,
        use_mock=args.mock,
    )

    summary = await runner.run()
    print("\n--- 统计摘要 ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
