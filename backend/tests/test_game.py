"""核心引擎测试 — 使用 Mock LLM 跑通一局."""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm.mock_client import MockLLMClient
from app.models.game import GameConfig
from app.models.enums import Team
from app.engine.game_master import GameMaster


async def test_one_game() -> None:
    """运行一局 9 人局（3狼+3民+1预+1女+1猎），验证引擎完整流程."""
    config = GameConfig(
        player_count=9,
        werewolf_count=3,
        seer_count=1,
        witch_count=1,
        hunter_count=1,
    )
    llm = MockLLMClient()
    gm = GameMaster(config=config, llm_client=llm)

    winner = await gm.run()

    assert winner in (Team.GOOD, Team.WEREWOLF), f"意外的获胜者: {winner}"
    assert gm.game_state.round_num >= 1, "游戏至少进行一轮"
    assert gm.game_log.total_rounds > 0

    print(f"\n✅ 测试通过! 获胜阵营: {winner.value}, 进行了 {gm.game_state.round_num} 轮")

    # 统计存活情况
    alive = [p for p in gm.players if p.alive]
    print(f"   最终存活: {[(p.player_id, p.role.value) for p in alive]}")


if __name__ == "__main__":
    asyncio.run(test_one_game())
