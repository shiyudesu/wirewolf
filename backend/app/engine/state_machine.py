"""游戏状态机 — 管理阶段流转."""

from __future__ import annotations

from transitions import Machine

from app.models.enums import Phase


class GameStateMachine:
    """狼人杀阶段状态机."""

    states = [
        Phase.SETUP.value,
        Phase.NIGHT_WEREWOLF.value,
        Phase.NIGHT_SEER.value,
        Phase.NIGHT_WITCH.value,
        Phase.DAY_ANNOUNCE.value,
        Phase.DAY_DISCUSS.value,
        Phase.DAY_VOTE.value,
        Phase.DAY_EXECUTION.value,
        Phase.GAME_OVER.value,
    ]

    def __init__(self) -> None:
        self.machine = Machine(
            model=self,
            states=GameStateMachine.states,
            initial=Phase.SETUP.value,
        )

        # 定义阶段转移
        transitions = [
            {"trigger": "start", "source": Phase.SETUP.value, "dest": Phase.NIGHT_WEREWOLF.value},
            {"trigger": "next", "source": Phase.NIGHT_WEREWOLF.value, "dest": Phase.NIGHT_SEER.value},
            {"trigger": "next", "source": Phase.NIGHT_SEER.value, "dest": Phase.NIGHT_WITCH.value},
            {"trigger": "next", "source": Phase.NIGHT_WITCH.value, "dest": Phase.DAY_ANNOUNCE.value},
            {"trigger": "next", "source": Phase.DAY_ANNOUNCE.value, "dest": Phase.DAY_DISCUSS.value},
            {"trigger": "next", "source": Phase.DAY_DISCUSS.value, "dest": Phase.DAY_VOTE.value},
            {"trigger": "next", "source": Phase.DAY_VOTE.value, "dest": Phase.DAY_EXECUTION.value},
            {"trigger": "next", "source": Phase.DAY_EXECUTION.value, "dest": Phase.NIGHT_WEREWOLF.value},
            {"trigger": "end", "source": "*", "dest": Phase.GAME_OVER.value},
        ]
        for t in transitions:
            self.machine.add_transition(**t)

    @property
    def current_phase(self) -> Phase:
        return Phase(self.state)
