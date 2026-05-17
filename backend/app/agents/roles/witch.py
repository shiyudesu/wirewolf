"""女巫 Agent."""

from app.models.enums import Role, ActionType
from app.agents.base import BaseAgent
from app.models.action import Observation


class WitchAgent(BaseAgent):
    """女巫 — 有一瓶解药和一瓶毒药，每瓶只能用一次."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.has_antidote = True
        self.has_poison = True

    def _role_desc(self) -> str:
        return (
            "你是女巫。你有一瓶解药和一瓶毒药，整局游戏各只能用一次。\n"
            "- 解药：夜晚得知狼人刀了谁，可以选择救他（第一晚可以自救）\n"
            "- 毒药：夜晚可以选择毒杀一名玩家\n"
            "请谨慎使用解药和毒药，它们是好人的重要资源。"
        )

    @property
    def action_space(self) -> list[ActionType]:
        actions = [ActionType.SPEAK, ActionType.VOTE]
        if self.has_antidote:
            actions.append(ActionType.SAVE)
        if self.has_poison:
            actions.append(ActionType.POISON)
        return actions

    def get_role_strategy_context(self, observation: Observation) -> str:
        phase = observation.phase
        if "night" in phase.lower():
            ctx = "【女巫夜间策略】\n"
            if self.has_antidote:
                ctx += (
                    "1. 解药使用：如果刀口是预言家/你/确认的好人，优先救\n"
                    "2. 第一晚可以自救，但后续不建议浪费解药自救（除非你是最后一神）\n"
                    "3. 如果刀口不明身份且解药只剩一瓶，谨慎使用\n"
                )
            if self.has_poison:
                ctx += (
                    "4. 毒药使用：只有高度怀疑某人是狼人时才毒，宁晚开不盲毒\n"
                    "5. 如果白天有人悍跳预言家且逻辑不通，夜间可直接毒他\n"
                    "6. 毒药是最后的底牌，留给最像狼的人"
                )
            return ctx
        else:
            return (
                "【女巫白天策略】\n"
                "1. 隐藏身份，不要过早暴露自己是女巫\n"
                "2. 可以通过'银水'信息（你救过的人）侧面帮助好人分析\n"
                "3. 如果解药已用且你身份暴露，争取在死前用掉毒药\n"
                "4. 发言阶段可以适当暗示自己有信息，但不要明确说自己是女巫"
            )
