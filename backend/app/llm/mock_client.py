"""Mock LLM 客户端 — 用于无 API 环境下的快速测试."""

from __future__ import annotations

import json
import random
from typing import Any

from app.models.enums import ActionType, Role


class MockLLMClient:
    """模拟 LLM，根据角色和场景返回合理的确定性/随机决策."""

    def __init__(self, model: str = "mock", temperature: float = 0.7, seed: int | None = None, **kwargs) -> None:
        self.model = model
        self.temperature = temperature
        self._counter = 0
        # Use a random seed per instance for true variance across games.
        # Can be overridden for reproducible tests.
        self._base_seed = seed if seed is not None else random.randint(0, 1_000_000)

    def _rng(self, agent_id: int = 1) -> random.Random:
        """每个 agent 有独立的随机数生成器，避免状态污染."""
        return random.Random(self._base_seed + agent_id * 997 + self._counter)

    async def chat(self, **kwargs) -> str:
        return "mock response"

    async def chat_json(self, messages: list[dict], **kwargs) -> dict[str, Any]:
        """解析 prompt 内容，返回对应角色的结构化决策."""
        self._counter += 1
        user_msg = ""
        for m in messages:
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        # 从 system prompt 中解析角色和玩家ID
        role = self._extract_role(messages)
        player_id = self._extract_player_id(messages)

        # 从 user prompt 中解析阶段
        phase = self._extract_phase(user_msg)

        # 解析存活玩家
        alive_ids = self._extract_alive_players(user_msg)

        return self._decide(role, player_id, phase, alive_ids, user_msg)

    async def chat_with_schema(self, messages: list[dict], schema: dict, **kwargs) -> dict[str, Any]:
        return await self.chat_json(messages)

    # ------------------------------------------------------------------ #
    # 解析辅助
    # ------------------------------------------------------------------ #

    def _extract_role(self, messages: list[dict]) -> Role:
        for m in messages:
            if m.get("role") == "system":
                content = m.get("content", "")
                if "werewolf" in content.lower() or "狼人" in content:
                    return Role.WEREWOLF
                elif "seer" in content.lower() or "预言家" in content:
                    return Role.SEER
                elif "witch" in content.lower() or "女巫" in content:
                    return Role.WITCH
                elif "hunter" in content.lower() or "猎人" in content:
                    return Role.HUNTER
        return Role.VILLAGER

    def _extract_player_id(self, messages: list[dict]) -> int:
        for m in messages:
            if m.get("role") == "system":
                content = m.get("content", "")
                # 匹配 "座位号是 X 号"
                import re
                match = re.search(r"座位号是\s*(\d+)\s*号", content)
                if match:
                    return int(match.group(1))
        return 1

    def _extract_phase(self, user_msg: str) -> str:
        if "night_werewolf" in user_msg.lower() or "狼人" in user_msg and "夜间" in user_msg:
            return "night_werewolf"
        elif "night_seer" in user_msg.lower() or "查验" in user_msg:
            return "night_seer"
        elif "night_witch" in user_msg.lower() or "解药" in user_msg or "毒药" in user_msg:
            return "night_witch"
        elif "day_discuss" in user_msg.lower() or "发言" in user_msg:
            return "day_discuss"
        elif "day_vote" in user_msg.lower() or "投票" in user_msg:
            return "day_vote"
        elif "day_execution" in user_msg.lower() or "被放逐" in user_msg:
            return "day_execution"
        elif "day_announce" in user_msg.lower():
            return "day_announce"
        return "unknown"

    def _extract_alive_players(self, user_msg: str) -> list[int]:
        import re
        # 匹配 "X号(存活)" 或 "X号"
        ids = []
        for line in user_msg.split("\n"):
            matches = re.findall(r"(\d+)号\s*\(存活\)", line)
            ids.extend([int(m) for m in matches])
        return ids

    # ------------------------------------------------------------------ #
    # 决策逻辑
    # ------------------------------------------------------------------ #

    def _decide(
        self, role: Role, player_id: int, phase: str, alive_ids: list[int], user_msg: str
    ) -> dict[str, Any]:
        others = [i for i in alive_ids if i != player_id]

        if phase == "night_werewolf":
            target = self._rng(player_id).choice(others) if others else None
            return {
                "action_type": "kill",
                "target_id": target,
                "content": "",
                "reasoning": f"随机选择 {target}号 作为击杀目标",
            }

        elif phase == "night_seer":
            target = self._rng(player_id).choice(others) if others else None
            return {
                "action_type": "check",
                "target_id": target,
                "content": "",
                "reasoning": f"随机查验 {target}号",
            }

        elif phase == "night_witch":
            # 检查是否有人被杀
            has_kill = "被狼人杀了" in user_msg
            has_antidote = "解药剩余: 有" in user_msg
            has_poison = "毒药剩余: 有" in user_msg

            if has_kill and has_antidote and self._rng(player_id).random() < 0.7:
                # 救人
                import re
                match = re.search(r"(\d+)号\s*被狼人杀了", user_msg)
                target = int(match.group(1)) if match else None
                return {
                    "action_type": "save",
                    "target_id": target,
                    "content": "",
                    "reasoning": f"使用解药救 {target}号",
                }
            elif has_poison and self._rng(player_id).random() < 0.3:
                target = self._rng(player_id).choice(others) if others else None
                return {
                    "action_type": "poison",
                    "target_id": target,
                    "content": "",
                    "reasoning": f"使用毒药毒 {target}号",
                }
            else:
                return {
                    "action_type": "pass",
                    "target_id": None,
                    "content": "",
                    "reasoning": "选择不使用技能",
                }

        elif phase == "day_discuss":
            speeches = [
                "我是好人，大家跟我走。",
                "我觉得前面有人发言有问题，需要重点关注。",
                "我是平民，没什么信息，听大家分析。",
                "有人跳预言家吗？我想听一下查验。",
                "这轮我们需要仔细听发言，找狼坑。",
            ]
            return {
                "action_type": "speak",
                "target_id": None,
                "content": self._rng(player_id).choice(speeches),
                "reasoning": "正常发言",
            }

        elif phase == "day_vote":
            # 好人方有更高概率集中投票（模拟推理行为）
            # 狼人则分散投票以隐藏身份
            rng = self._rng(player_id)
            if role == Role.WEREWOLF:
                target = rng.choice(others) if others else None
            else:
                # 好人方：50% 概率随机投票，50% 概率随机跟随一个"共识"目标
                if others:
                    if rng.random() < 0.5:
                        target = rng.choice(others)
                    else:
                        # 随机选择共识目标（非确定性，依赖实例种子）
                        target = rng.choice(others)
                else:
                    target = None
            return {
                "action_type": "vote",
                "target_id": target,
                "content": "",
                "reasoning": f"投票给 {target}号",
            }

        elif phase == "day_execution":
            # 猎人开枪
            if role == Role.HUNTER and self._rng(player_id).random() < 0.5:
                target = self._rng(player_id).choice(others) if others else None
                return {
                    "action_type": "shoot",
                    "target_id": target,
                    "content": "",
                    "reasoning": f"带走 {target}号",
                }
            else:
                return {
                    "action_type": "pass",
                    "target_id": None,
                    "content": "",
                    "reasoning": "选择不行动",
                }

        return {
            "action_type": "pass",
            "target_id": None,
            "content": "",
            "reasoning": "默认通过",
        }
