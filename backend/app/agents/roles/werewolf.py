"""狼人 Agent."""

from app.models.enums import Role, ActionType
from app.agents.base import BaseAgent
from app.models.action import Observation


class WerewolfAgent(BaseAgent):
    """狼人 — 夜间可以杀人，白天需要伪装成好人."""

    def _role_desc(self) -> str:
        return (
            "你是狼人。你的目标是与狼队友合作，在夜间杀死好人，"
            "白天通过发言伪装成好人，误导其他玩家投票放逐好人。"
            "当所有好人（神职+平民）全部死亡时，狼人阵营胜利。"
        )

    @property
    def action_space(self) -> list[ActionType]:
        return [ActionType.KILL, ActionType.SPEAK, ActionType.VOTE]

    def get_role_strategy_context(self, observation: Observation) -> str:
        phase = observation.phase
        if "night" in phase.lower():
            return (
                "【狼人夜间策略】\n"
                "1. 优先刀神职（预言家 > 女巫 > 猎人），避免刀猎人（可能被反杀）\n"
                "2. 如果某玩家被多人怀疑是神职，优先刀他\n"
                "3. 与队友协商时，给出明确的刀人理由，争取统一意见\n"
                "4. 注意：女巫可能有解药，第一晚刀口可能被救"
            )
        else:
            return (
                "【狼人白天策略】\n"
                "1. 发言要模仿好人逻辑，避免过度攻击或过度防守\n"
                "2. 可以适当攻击狼队友（做身份），但不要过于明显\n"
                "3. 如果预言家已跳，考虑是否悍跳预言家扰乱局势\n"
                "4. 投票阶段：如果狼队友被集火，尝试分散火力；"
                "如果好人被怀疑，推波助澜引导投票"
            )
