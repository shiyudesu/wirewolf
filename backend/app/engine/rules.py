"""狼人杀规则与胜负裁决."""

from __future__ import annotations

from typing import Optional

from app.models.enums import Role, Team
from app.models.game import Player


class GameRules:
    """游戏规则计算类."""

    @staticmethod
    def determine_winner(players: list[Player]) -> Optional[Team]:
        """判断当前游戏是否结束，返回获胜阵营或 None."""
        alive = [p for p in players if p.alive]
        alive_werewolves = [p for p in alive if p.role == Role.WEREWOLF]
        alive_good = [p for p in alive if p.team == Team.GOOD]

        # 狼人全灭 -> 好人胜利
        if not alive_werewolves:
            return Team.GOOD

        # 好人全灭（神+民死完）-> 狼人胜利
        if not alive_good:
            return Team.WEREWOLF

        # 屠边规则：神职死完 或 平民死完 -> 狼人胜利
        alive_gods = [p for p in alive if p.role in (Role.SEER, Role.WITCH, Role.HUNTER)]
        alive_villagers = [p for p in alive if p.role == Role.VILLAGER]
        if not alive_gods or not alive_villagers:
            return Team.WEREWOLF

        return None

    @staticmethod
    def get_team(role: Role) -> Team:
        if role == Role.WEREWOLF:
            return Team.WEREWOLF
        return Team.GOOD

    @staticmethod
    def role_distribution(config: dict) -> list[Role]:
        """根据配置生成角色列表."""
        roles: list[Role] = []
        roles.extend([Role.WEREWOLF] * config["werewolf_count"])
        roles.extend([Role.SEER] * config["seer_count"])
        roles.extend([Role.WITCH] * config["witch_count"])
        roles.extend([Role.HUNTER] * config["hunter_count"])
        villagers = config["player_count"] - len(roles)
        roles.extend([Role.VILLAGER] * villagers)
        return roles
