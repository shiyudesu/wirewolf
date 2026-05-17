"""游戏核心数据模型."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional

from .enums import Role, Team, Phase


class Player(BaseModel):
    """玩家（人类或Agent）."""

    player_id: int = Field(..., description="玩家座位号，从1开始")
    name: str = Field(..., description="玩家名称")
    role: Role = Field(..., description="角色")
    team: Team = Field(..., description="阵营")
    alive: bool = Field(default=True, description="是否存活")
    is_human: bool = Field(default=False, description="是否为人类玩家")


class GameConfig(BaseModel):
    """游戏配置."""

    player_count: int = Field(default=12, ge=6, le=18)
    werewolf_count: int = Field(default=4, ge=1)
    seer_count: int = Field(default=1, ge=0)
    witch_count: int = Field(default=1, ge=0)
    hunter_count: int = Field(default=1, ge=0)
    # 其余自动为平民

    def validate(self) -> None:
        total_special = (
            self.werewolf_count
            + self.seer_count
            + self.witch_count
            + self.hunter_count
        )
        if total_special > self.player_count:
            raise ValueError("特殊角色总数不能超过玩家总数")
        if self.seer_count > 1:
            raise ValueError("当前引擎仅支持单预言家")
        if self.witch_count > 1:
            raise ValueError("当前引擎仅支持单女巫")
        if self.hunter_count > 1:
            raise ValueError("当前引擎仅支持单猎人")


class GameState(BaseModel):
    """游戏状态快照."""

    game_id: str = Field(..., description="对局唯一ID")
    phase: Phase = Field(default=Phase.SETUP)
    round_num: int = Field(default=0, description="当前轮次，从1开始")
    players: list[Player] = Field(default_factory=list)
    alive_players: list[int] = Field(default_factory=list)
    winner: Optional[Team] = Field(default=None)
