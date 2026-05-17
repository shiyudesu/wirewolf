"""猎人 Agent."""

from app.models.enums import Role, ActionType
from app.agents.base import BaseAgent
from app.models.action import Observation


class HunterAgent(BaseAgent):
    """猎人 — 被放逐或毒杀时可以开枪带走一人（被刀不能开枪）."""

    def _role_desc(self) -> str:
        return (
            "你是猎人。当你被投票放逐时，你可以开枪带走一名玩家。"
            "如果你被女巫毒死或在夜间被刀，你不能开枪。"
            "你是好人阵营的神职，需要协助预言家找出狼人。"
        )

    @property
    def action_space(self) -> list[ActionType]:
        return [ActionType.SHOOT, ActionType.SPEAK, ActionType.VOTE]

    def get_role_strategy_context(self, observation: Observation) -> str:
        phase = observation.phase
        if "execution" in phase.lower():
            return (
                "【猎人开枪策略】\n"
                "1. 如果你确定某人是狼人，优先开枪带走他\n"
                "2. 如果没有明确目标，选择发言最差/最可疑的玩家\n"
                "3. 避免带走疑似神职（预言家、女巫）\n"
                "4. 如果场上狼人明显劣势，可以考虑不开枪避免误伤"
            )
        elif "night" in phase.lower():
            return (
                "【猎人夜间策略】\n"
                "1. 夜间无行动，但白天发言要注意隐藏身份\n"
                "2. 避免成为狼人的目标（狼人可能故意刀你让你无法开枪）"
            )
        else:
            return (
                "【猎人白天策略】\n"
                "1. 隐藏身份，不要暴露自己是猎人（除非需要威慑狼人）\n"
                "2. 发言逻辑清晰，帮助好人分析\n"
                "3. 如果狼人知道你是猎人，他们可能优先放逐你（让你开枪），"
                "此时要争取好人的保护"
            )
