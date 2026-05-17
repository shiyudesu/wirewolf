"""退化防护 — 防止策略修改后表现变差."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from app.llm.client import LLMClient
from app.models.log import AgentProfile


@dataclass
class GuardResult:
    """防护检查结果."""

    approved: bool
    reason: str
    rollback_recommended: bool = False


class DegenerationGuard:
    """策略退化防护系统."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(temperature=0.3)

    def check_metrics(
        self,
        old_metrics: dict[str, float],
        new_metrics: dict[str, float],
        key_metrics: list[str] | None = None,
    ) -> GuardResult:
        """基于指标对比判断是否退化.

        规则:
        1. 新版本必须至少在一个关键指标上不比旧版本差
        2. 如果胜率下降超过 10%，标记为可能退化
        3. 如果连续 3 个新版本表现更差，建议回滚
        """
        keys = key_metrics or ["win_rate", "avg_score", "avg_survival"]

        improvements = 0
        degradations = 0
        details = []

        for k in keys:
            old_v = old_metrics.get(k, 0)
            new_v = new_metrics.get(k, 0)
            delta = new_v - old_v
            details.append(f"  {k}: {old_v:.3f} -> {new_v:.3f} (Δ{delta:+.3f})")

            if delta > 0.001:
                improvements += 1
            elif delta < -0.001:
                degradations += 1

        print("\n".join(details))

        # 如果所有关键指标都下降，判定为退化
        if improvements == 0 and degradations > 0:
            return GuardResult(
                approved=False,
                reason=f"所有关键指标均下降 ({degradations}/{len(keys)})",
                rollback_recommended=degradations >= len(keys),
            )

        # 胜率下降超过 10% 警告
        win_delta = new_metrics.get("win_rate", 0) - old_metrics.get("win_rate", 0)
        if win_delta < -0.1:
            return GuardResult(
                approved=False,
                reason=f"胜率大幅下降 ({win_delta:+.1%})",
                rollback_recommended=True,
            )

        return GuardResult(
            approved=True,
            reason=f"至少 {improvements} 个指标有提升",
        )

    async def llm_self_review(
        self,
        old_profile: AgentProfile,
        new_profile: AgentProfile,
    ) -> GuardResult:
        """让 LLM 自审新策略是否有逻辑矛盾."""
        prompt = (
            f"你正在审查一份狼人杀策略更新。请检查新策略是否存在逻辑矛盾或不合理之处。\n\n"
            f"【旧策略 v{old_profile.version}】\n"
            f"{old_profile.strategy_notes or '（无）'}\n\n"
            f"【新策略 v{new_profile.version}】\n"
            f"{new_profile.strategy_notes}\n\n"
            f"请输出 JSON：\n"
            f"{{'has_contradiction': true/false, 'issues': ['...'], 'approval': true/false}}"
        )

        try:
            result = await self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是策略逻辑审查专家。只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ]
            )
            approved = result.get("approval", True)
            issues = result.get("issues", [])
            return GuardResult(
                approved=approved,
                reason="LLM 自审通过" if approved else f"发现逻辑问题: {'; '.join(issues)}",
            )
        except Exception as e:
            print(f"LLM 自审失败: {e}")
            # 自审失败时保守通过
            return GuardResult(approved=True, reason="自审失败，保守通过")

    def should_rollback(
        self,
        version_history: list[dict[str, float]],
        threshold: int = 3,
    ) -> bool:
        """判断是否应该回滚到历史最佳版本.

        如果连续 threshold 个新版本表现都比上一个版本差，建议回滚。
        """
        if len(version_history) < threshold + 1:
            return False

        # 检查最近 threshold 次是否都是下降
        recent = version_history[-threshold:]
        for i in range(len(recent)):
            if i == 0:
                prev = version_history[-(threshold + 1)]
            else:
                prev = recent[i - 1]
            curr = recent[i]
            if curr.get("score", 0) >= prev.get("score", 0):
                return False

        return True
