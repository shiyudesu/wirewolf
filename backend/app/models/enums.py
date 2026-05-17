"""游戏枚举定义."""

from enum import Enum, auto


class Role(str, Enum):
    """角色枚举."""

    WEREWOLF = "werewolf"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    VILLAGER = "villager"


class Team(str, Enum):
    """阵营枚举."""

    WEREWOLF = "werewolf"
    GOOD = "good"


class Phase(str, Enum):
    """游戏阶段枚举."""

    SETUP = "setup"
    NIGHT_WEREWOLF = "night_werewolf"
    NIGHT_SEER = "night_seer"
    NIGHT_WITCH = "night_witch"
    DAY_ANNOUNCE = "day_announce"
    DAY_DISCUSS = "day_discuss"
    DAY_VOTE = "day_vote"
    DAY_EXECUTION = "day_execution"
    GAME_OVER = "game_over"


class ActionType(str, Enum):
    """动作类型枚举."""

    KILL = "kill"
    SAVE = "save"
    POISON = "poison"
    CHECK = "check"
    SHOOT = "shoot"
    SPEAK = "speak"
    VOTE = "vote"
    PASS = "pass"
