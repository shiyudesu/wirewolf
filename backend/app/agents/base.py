"""BaseAgent — 通用Agent抽象基类."""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Any

from app.llm.client import LLMClient
from app.models.enums import Role, ActionType, Phase
from app.models.action import Observation, Action
from app.models.log import AgentProfile, ThoughtRecord, Message
from app.agents.memory import ConversationBuffer


class BaseAgent(ABC):
    """狼人杀通用Agent基类.

    所有角色Agent必须继承此类，实现 act() 方法。
    """

    def __init__(
        self,
        agent_id: int,
        role: Role,
        llm_client: LLMClient,
        profile: Optional[AgentProfile] = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.alive = True
        self.llm = llm_client
        self.memory = ConversationBuffer()
        self.profile = profile or self._default_profile()

    def _default_profile(self) -> AgentProfile:
        return AgentProfile(
            role_description=self._role_desc(),
            strategy_notes="",
            persona="冷静理性的玩家",
            version=1,
        )

    @abstractmethod
    def _role_desc(self) -> str:
        """返回角色描述文本."""
        ...

    @property
    @abstractmethod
    def action_space(self) -> list[ActionType]:
        """该角色可执行的动作列表."""
        ...

    # ------------------------------------------------------------------ #
    # 核心决策接口
    # ------------------------------------------------------------------ #

    async def act(self, observation: Observation) -> tuple[Action, list[dict], dict]:
        """根据观察做出决策，返回 (动作, LLM prompt messages, LLM response dict)."""
        # 1. 记录本轮观察（私有思考）
        self._record_observation(observation)

        # 2. 构造 LLM Prompt
        messages = self._build_prompt(observation)

        # 3. 调用 LLM，获取结构化输出
        schema = self._action_schema()
        try:
            result = await self.llm.chat_with_schema(
                messages=messages,
                schema=schema,
                temperature=0.5,
            )
        except Exception:
            # fallback: JSON mode
            result = await self.llm.chat_json(messages=messages, temperature=0.5)

        # 4. 解析为 Action
        action = self._parse_action(result, observation)

        # 5. 记录推理到私有记忆
        self.memory.add_thought(
            ThoughtRecord(
                round_num=observation.round_num,
                phase=Phase(observation.phase),
                content=f"推理: {result.get('reasoning', '无')}\n决定: {action.action_type.value}"
                + (f" 目标{action.target_id}" if action.target_id else ""),
            )
        )

        return action, messages, result

    # ------------------------------------------------------------------ #
    # Prompt 构造
    # ------------------------------------------------------------------ #

    def _build_prompt(self, observation: Observation) -> list[dict[str, str]]:
        system_msg = self._system_prompt()
        user_msg = self._user_prompt(observation)
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def _system_prompt(self) -> str:
        return (
            f"你是一名狼人杀玩家，你的座位号是 {self.agent_id} 号。\n"
            f"你的角色是: {self.role.value}\n"
            f"角色描述: {self.profile.role_description}\n"
            f"你的性格: {self.profile.persona}\n"
            f"当前策略笔记 (v{self.profile.version}): {self.profile.strategy_notes or '暂无'}\n\n"
            "规则提醒:\n"
            "- 狼人杀是推理博弈游戏，好人阵营需要找出所有狼人，狼人阵营需要杀光好人。\n"
            "- 白天可以发言和投票，晚上根据角色执行技能。\n"
            "- 你必须根据场上信息做出最优决策。\n"
            "- 输出必须是 JSON 格式。"
        )

    def get_role_strategy_context(self, observation: Observation) -> str:
        """返回角色特化的策略上下文（子类可覆盖）."""
        return ""

    def _user_prompt(self, observation: Observation) -> str:
        recent_public = self.memory.summarize_public(max_chars=1500)
        recent_private = "\n".join(
            [
                f"第{t.round_num}轮 {t.phase.value}: {t.content}"
                for t in self.memory.get_recent_thoughts(5)
            ]
        )

        players_info = "\n".join(
            [
                f"  {p['player_id']}号{'(存活)' if p.get('alive') else '(已死亡)' }"
                for p in observation.players_status
            ]
        )

        # 角色特化策略提示
        role_context = self.get_role_strategy_context(observation)
        role_context_str = f"\n【角色策略提示】\n{role_context}\n" if role_context else ""

        return (
            f"【当前阶段】第 {observation.round_num} 轮 - {observation.phase}\n"
            f"【存活玩家】\n{players_info}\n\n"
            f"【本轮私有信息】\n{observation.private_info or '无'}\n\n"
            f"【公共信息摘要】\n{recent_public}\n\n"
            f"【你的近期思考】\n{recent_private or '无'}\n\n"
            f"【可用动作】{[a.value for a in self.action_space]}\n"
            f"{role_context_str}\n"
            "请输出你的决策，格式要求如下 JSON：\n"
            "```json\n"
            "{\n"
            '  "action_type": "动作类型",\n'
            '  "target_id": 目标玩家ID或null,\n'
            '  "content": "发言内容（如果是speak）或空字符串",\n'
            '  "reasoning": "你的推理过程（中文）"\n'
            "}\n"
            "```"
        )

    def _action_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": [a.value for a in self.action_space],
                    "description": "你要执行的动作类型",
                },
                "target_id": {
                    "type": ["integer", "null"],
                    "description": "目标玩家ID，无目标则填null",
                },
                "content": {
                    "type": "string",
                    "description": "发言内容或其他文本信息",
                },
                "reasoning": {
                    "type": "string",
                    "description": "你的推理过程",
                },
            },
            "required": ["action_type", "reasoning"],
        }

    def _parse_action(self, result: dict, observation: Observation) -> Action:
        action_type_str = result.get("action_type", "pass")
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            action_type = ActionType.PASS

        # 安全检查：该角色是否有权限执行此动作
        if action_type not in self.action_space:
            action_type = ActionType.PASS

        # 安全检查：禁止对死亡玩家使用技能
        target_id = result.get("target_id")
        alive_ids = {p["player_id"] for p in observation.players_status if p.get("alive")}
        if target_id is not None and target_id not in alive_ids:
            target_id = None

        # 女巫不能对自己用毒药；解药第一晚可自救，后续不可（由 GameMaster 控制轮次）
        if self.role == Role.WITCH and target_id == self.agent_id:
            if action_type == ActionType.POISON:
                target_id = None
            # SAVE 允许（第一晚自救在 GameMaster 中控制）

        return Action(
            agent_id=self.agent_id,
            action_type=action_type,
            target_id=target_id,
            content=result.get("content", ""),
            reasoning=result.get("reasoning", ""),
        )

    def _record_observation(self, observation: Observation) -> None:
        """将观察记录到记忆中."""
        self.memory.add_message(
            Message(
                round_num=observation.round_num,
                phase=Phase(observation.phase),
                speaker_id=0,  # 系统消息
                content=f"阶段: {observation.phase} | 公共: {observation.public_info}",
                msg_type="system",
            )
        )

    # ------------------------------------------------------------------ #
    # 自我反思与策略修改（方向①核心）
    # ------------------------------------------------------------------ #

    async def reflect_after_game(
        self,
        game_log: str,
        won: bool,
        key_decisions: list[dict[str, Any]],
    ) -> AgentProfile:
        """局后反思，返回更新后的 AgentProfile."""
        prompt = (
            f"你是一局狼人杀的复盘阶段。你是 {self.agent_id} 号玩家，"
            f"角色是 {self.role.value}。\n"
            f"本局结果: {'胜利' if won else '失败'}\n\n"
            f"【当前策略笔记 v{self.profile.version}】\n"
            f"{self.profile.strategy_notes or '暂无'}\n\n"
            f"【关键决策回顾】\n"
        )
        for d in key_decisions:
            prompt += (
                f"- 第{d['round']}轮 {d['phase']}: "
                f"你选择了 {d['action']}，"
                f"结果是 {d.get('outcome', '未知')}\n"
            )

        prompt += (
            f"\n【对局日志摘要】\n{game_log[:3000]}\n\n"
            "请复盘你的表现，分析胜利/失败的原因，"
            "并更新你的 strategy_notes，以便在下一局表现得更好。\n"
            "输出格式: JSON，包含字段: updated_strategy (string), reflection (string)"
        )

        try:
            result = await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是一名狼人杀策略分析师。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
        except Exception:
            result = {"updated_strategy": self.profile.strategy_notes, "reflection": "复盘失败"}

        new_strategy = result.get("updated_strategy", self.profile.strategy_notes)
        # 如果策略确实改变了，才增加版本号
        if new_strategy != self.profile.strategy_notes:
            self.profile.strategy_notes = new_strategy
            self.profile.version += 1

        self.memory.add_thought(
            ThoughtRecord(
                round_num=0,
                phase=Phase.GAME_OVER,
                content=f"局后反思: {result.get('reflection', '')}\n"
                f"策略更新 v{self.profile.version}: {new_strategy[:200]}",
            )
        )
        return self.profile

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #

    def on_death(self) -> None:
        self.alive = False

    def receive_public_message(self, message: Message) -> None:
        self.memory.add_message(message)

    def get_memory_summary(self) -> str:
        return self.memory.summarize_public()
