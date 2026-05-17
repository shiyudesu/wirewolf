"""规则引擎单元测试."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.enums import Role, Team
from app.models.game import Player
from app.engine.rules import GameRules


def test_werewolf_win_all_good_dead() -> None:
    players = [
        Player(player_id=1, name="P1", role=Role.WEREWOLF, team=Team.WEREWOLF, alive=True),
        Player(player_id=2, name="P2", role=Role.VILLAGER, team=Team.GOOD, alive=False),
        Player(player_id=3, name="P3", role=Role.SEER, team=Team.GOOD, alive=False),
    ]
    assert GameRules.determine_winner(players) == Team.WEREWOLF


def test_good_win_all_wolves_dead() -> None:
    players = [
        Player(player_id=1, name="P1", role=Role.WEREWOLF, team=Team.WEREWOLF, alive=False),
        Player(player_id=2, name="P2", role=Role.VILLAGER, team=Team.GOOD, alive=True),
        Player(player_id=3, name="P3", role=Role.SEER, team=Team.GOOD, alive=True),
    ]
    assert GameRules.determine_winner(players) == Team.GOOD


def test_werewolf_win_gods_dead() -> None:
    """屠边规则：神职死完，狼人胜利."""
    players = [
        Player(player_id=1, name="P1", role=Role.WEREWOLF, team=Team.WEREWOLF, alive=True),
        Player(player_id=2, name="P2", role=Role.VILLAGER, team=Team.GOOD, alive=True),
        Player(player_id=3, name="P3", role=Role.SEER, team=Team.GOOD, alive=False),
        Player(player_id=4, name="P4", role=Role.WITCH, team=Team.GOOD, alive=False),
        Player(player_id=5, name="P5", role=Role.HUNTER, team=Team.GOOD, alive=False),
    ]
    assert GameRules.determine_winner(players) == Team.WEREWOLF


def test_game_continues() -> None:
    """双方都有人存活，游戏继续."""
    players = [
        Player(player_id=1, name="P1", role=Role.WEREWOLF, team=Team.WEREWOLF, alive=True),
        Player(player_id=2, name="P2", role=Role.VILLAGER, team=Team.GOOD, alive=True),
        Player(player_id=3, name="P3", role=Role.SEER, team=Team.GOOD, alive=True),
    ]
    assert GameRules.determine_winner(players) is None


def test_role_distribution() -> None:
    config = {
        "player_count": 9,
        "werewolf_count": 3,
        "seer_count": 1,
        "witch_count": 1,
        "hunter_count": 1,
    }
    roles = GameRules.role_distribution(config)
    assert len(roles) == 9
    assert roles.count(Role.WEREWOLF) == 3
    assert roles.count(Role.SEER) == 1
    assert roles.count(Role.WITCH) == 1
    assert roles.count(Role.HUNTER) == 1
    assert roles.count(Role.VILLAGER) == 3


if __name__ == "__main__":
    test_werewolf_win_all_good_dead()
    test_good_win_all_wolves_dead()
    test_werewolf_win_gods_dead()
    test_game_continues()
    test_role_distribution()
    print("✅ 所有规则测试通过")
