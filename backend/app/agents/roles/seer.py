"""预言家 Agent."""

from app.models.enums import Role, ActionType
from app.agents.base import BaseAgent
from app.models.action import Observation


class SeerAgent(BaseAgent):
    """预言家 — 夜间可以查验一名玩家是否为狼人."""

    def _role_desc(self) -> str:
        return (
            "你是预言家。每轮夜晚你可以查验一名存活玩家的身份，"
            "得知他是好人还是狼人。白天你应该通过发言向其他好人传递查验信息，"
            "带领好人找出狼人。注意保护自己，狼人会优先杀死暴露身份的预言家。"
        )

    @property
    def action_space(self) -> list[ActionType]:
        return [ActionType.CHECK, ActionType.SPEAK, ActionType.VOTE]

    def get_role_strategy_context(self, observation: Observation) -> str:
        phase = observation.phase
        if "night" in phase.lower():
            return (
                "【预言家夜间策略】\n"
                "1. 验人优先级：发言最可疑的 > 被多人保护的 > 从未被怀疑的（藏狼可能）\n"
                "2. 避免连续验同一个人\n"
                "3. 如果某人被女巫/猎人公开保过，他的身份价值较低，优先验其他人\n"
                "4. 记录所有查验结果，白天准确传递信息"
            )
        else:
            return (
                "【预言家白天策略】\n"
                "1. 跳身份时机：如果已验出狼人且自己可能下一晚被刀，果断跳身份报查验\n"
                "2. 如果已有狼人悍跳预言家，你必须立即对跳，否则好人会迷失\n"
                "3. 报查验时给出清晰的逻辑链：为什么验这个人 + 结果 + 下一步建议\n"
                "4. 不要透露接下来要验谁，避免狼人干扰"
            )
