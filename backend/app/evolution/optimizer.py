"""策略优化器 — 根据评测反馈生成新的 AgentProfile.strategy_notes."""

from __future__ import annotations

import json
from typing import Optional

from app.llm.client import LLMClient
from app.models.log import AgentProfile
from app.evaluation.leaderboard import LeaderboardDB


class StrategyOptimizer:
    """策略优化器，输入历史对局数据，输出新策略."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        db: Optional[LeaderboardDB] = None,
    ) -> None:
        self.llm = llm_client or LLMClient(temperature=0.7)
        self.db = db or LeaderboardDB()

    async def optimize(
        self,
        agent_id: int,
        role: str,
        current_profile: AgentProfile,
        recent_game_ids: list[str],
        target_metric: str = "win_rate",
    ) -> AgentProfile:
        """为指定 Agent 生成优化后的策略.

        Args:
            agent_id: Agent 座位号
            role: 角色类型
            current_profile: 当前策略配置
            recent_game_ids: 最近 N 局的游戏ID
            target_metric: 优化的目标指标
        """
        # 1. 收集历史表现数据
        performance = await self._collect_performance(agent_id, recent_game_ids)

        # 2. 构造 Prompt
        prompt = self._build_optimization_prompt(
            agent_id=agent_id,
            role=role,
            current_profile=current_profile,
            performance=performance,
            target_metric=target_metric,
        )

        # 3. 调用 LLM 生成新策略
        try:
            result = await self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一名顶级的狼人杀策略分析师和教练。"
                            "你的任务是根据玩家的历史表现数据，"
                            "为其制定更优秀的策略。策略要具体、可操作。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
        except Exception as e:
            print(f"策略优化失败: {e}")
            return current_profile

        new_strategy = result.get("new_strategy_notes", current_profile.strategy_notes)
        reflection = result.get("reflection", "")

        # 4. 生成新 Profile
        new_profile = AgentProfile(
            role_description=current_profile.role_description,
            strategy_notes=new_strategy,
            persona=current_profile.persona,
            version=current_profile.version + 1,
        )

        print(f"  Agent {agent_id} ({role}) 策略 v{current_profile.version} -> v{new_profile.version}")
        print(f"    反思: {reflection[:100]}...")
        print(f"    新策略: {new_strategy[:150]}...")

        return new_profile

    async def _collect_performance(self, agent_id: int, game_ids: list[str]) -> dict:
        """收集 Agent 在最近对局中的表现数据."""
        return await self.db.get_agent_performance(agent_id, game_ids)

    def _build_optimization_prompt(
        self,
        agent_id: int,
        role: str,
        current_profile: AgentProfile,
        performance: dict,
        target_metric: str,
    ) -> str:
        prompt = (
            f"# 狼人杀策略优化任务\n\n"
            f"## 玩家信息\n"
            f"- 座位号: {agent_id}\n"
            f"- 角色: {role}\n"
            f"- 当前策略版本: v{current_profile.version}\n"
            f"- 当前策略笔记:\n{current_profile.strategy_notes or '（暂无）'}\n\n"
            f"## 最近表现数据（最近 {performance['games']} 局）\n"
            f"- 胜率: {performance['win_rate']:.1%}\n"
            f"- 平均评分: {performance['avg_score']:.1f}/100\n"
            f"- 平均存活轮数: {performance['avg_survival']:.1f}\n\n"
        )

        # 详细数据
        if performance.get("details"):
            prompt += "## 逐局详情\n"
            for d in performance["details"][:5]:
                prompt += (
                    f"- 游戏 {d['game_id'][:8]}: "
                    f"{'胜利' if d['won'] else '失败'}, "
                    f"存活 {d['survival_rounds']} 轮, "
                    f"评分 {d['overall_score']:.1f}\n"
                )

        prompt += (
            f"\n## 优化目标\n"
            f"提升 {target_metric}，同时保持策略的可操作性。\n\n"
            f"## 输出要求\n"
            f"请输出 JSON：\n"
            f"```json\n"
            f"{{\n"
            f'  "reflection": "对当前表现的分析和问题诊断（中文）",\n'
            f'  "new_strategy_notes": "更新后的策略笔记（中文，具体可操作）",\n'
            f'  "expected_improvement": "预期改进效果"\n'
            f"}}\n"
            f"```"
        )

        return prompt
