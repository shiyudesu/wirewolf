"""LLM-as-a-Judge — 用 LLM 评估 Agent 表现."""

from __future__ import annotations

import json
from typing import Optional

from app.llm.client import LLMClient


class LLMJudge:
    """LLM 评审员，对 Agent 的发言和决策进行打分."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(temperature=0.3)

    async def judge_speech(
        self,
        speaker_role: str,
        speech: str,
        context: str,
        dimensions: list[str] | None = None,
    ) -> dict[str, float]:
        """评估单条发言质量.

        维度:
        - logic: 逻辑性 (1-10)
        - persuasion: 说服力 (1-10)
        - info_density: 信息密度 (1-10)
        - disguise: 伪装度 (仅狼人) (1-10)
        """
        dims = dimensions or ["logic", "persuasion", "info_density"]
        if speaker_role == "werewolf":
            dims.append("disguise")

        prompt = (
            f"你是一名专业的狼人杀裁判，请对以下发言进行评分。\n\n"
            f"【发言者角色】{speaker_role}\n"
            f"【游戏上下文】{context}\n\n"
            f"【发言内容】\n{speech}\n\n"
            f"请从以下维度打分（1-10分，10分最高）：\n"
            + "\n".join([f"- {d}: 请给出分数和一句话理由" for d in dims])
            + "\n\n输出 JSON 格式，例如: {\"logic\": 7, \"logic_reason\": \"...\"}"
        )

        try:
            result = await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是狼人杀发言质量评审专家。只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ]
            )
            scores = {}
            for d in dims:
                scores[d] = float(result.get(d, 5.0))
            return scores
        except Exception as e:
            print(f"LLM Judge 评分失败: {e}")
            return {d: 5.0 for d in dims}

    async def judge_defense(
        self,
        speech: str,
        situation: str,
    ) -> float:
        """评估被抗推时的辩护质量 (1-10)."""
        prompt = (
            f"你是一名狼人杀裁判。以下玩家面临被投票放逐，请评估其辩护质量。\n\n"
            f"【处境】{situation}\n"
            f"【辩护发言】\n{speech}\n\n"
            f"请给出 1-10 的分数和一句话理由。输出 JSON: {{\"score\": 7, \"reason\": \"...\"}}"
        )
        try:
            result = await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是狼人杀评审专家。只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ]
            )
            return float(result.get("score", 5.0))
        except Exception as e:
            print(f"LLM Judge 辩护评分失败: {e}")
            return 5.0

    async def judge_overall_strategy(
        self,
        game_summary: str,
        agent_role: str,
        key_decisions: list[dict],
    ) -> dict[str, Any]:
        """评估整局策略水平."""
        prompt = (
            f"请复盘一名 {agent_role} 玩家的整局表现。\n\n"
            f"【对局摘要】\n{game_summary}\n\n"
            f"【关键决策】\n"
        )
        for d in key_decisions:
            prompt += f"- 第{d['round']}轮: {d['action']}，结果: {d.get('outcome', '未知')}\n"

        prompt += (
            "\n请评估其策略水平，输出 JSON：\n"
            "{\"strategy_score\": 1-10, \"key_mistakes\": [\"...\"], \"strengths\": [\"...\"]}"
        )

        try:
            return await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是狼人杀策略分析师。只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as e:
            print(f"LLM Judge 策略评估失败: {e}")
            return {"strategy_score": 5.0, "key_mistakes": [], "strengths": []}
