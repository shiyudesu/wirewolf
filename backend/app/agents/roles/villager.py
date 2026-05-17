"""平民 Agent."""

from app.models.enums import Role, ActionType
from app.agents.base import BaseAgent
from app.models.action import Observation


class VillagerAgent(BaseAgent):
    """平民 — 无特殊技能，通过发言和投票帮助好人阵营."""

    def _role_desc(self) -> str:
        return (
            "你是平民。你没有特殊技能，但你和神职同属好人阵营。"
            "通过仔细观察发言、分析逻辑，找出狼人，在白天投票放逐他们。"
            "平民是好人阵营的基石，保护神职、团结一致才能获胜。"
        )

    @property
    def action_space(self) -> list[ActionType]:
        return [ActionType.SPEAK, ActionType.VOTE]

    def get_role_strategy_context(self, observation: Observation) -> str:
        phase = observation.phase
        if "night" in phase.lower():
            return (
                "【平民夜间策略】\n"
                "1. 夜间无行动，可以整理白天的信息\n"
                "2. 思考谁的发言有漏洞，谁可能是狼人"
            )
        else:
            return (
                "【平民白天策略】\n"
                "1. 认真听取所有发言，分析逻辑一致性\n"
                "2. 寻找发言中的矛盾点：前后不一致、过度防守、盲目跟票\n"
                "3. 如果预言家已跳，优先相信真预言家（对比查验逻辑和发言态度）\n"
                "4. 投票要有自己的判断，不要无脑跟票\n"
                "5. 如果你是金水（被预言家验过的好人），可以适当带队"
            )
