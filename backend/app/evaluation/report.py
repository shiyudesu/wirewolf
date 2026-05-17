"""复盘归因系统 — 自动生成 PostGameReport."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.evaluation.metrics import MetricsCalculator


@dataclass
class PostGameReport:
    """单局复盘报告."""

    game_id: str
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    winner: Optional[str] = None
    total_rounds: int = 0

    # 败因归因
    key_mistakes: list[dict] = field(default_factory=list)
    # 时间线
    timeline: list[dict] = field(default_factory=list)
    # 对比
    comparison: dict = field(default_factory=dict)
    # 各玩家评分
    player_scores: dict[int, float] = field(default_factory=dict)
    # 决策影响力
    pivotal_moments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "winner": self.winner,
            "total_rounds": self.total_rounds,
            "key_mistakes": self.key_mistakes,
            "timeline": self.timeline,
            "comparison": self.comparison,
            "player_scores": self.player_scores,
            "pivotal_moments": self.pivotal_moments,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


class ReportGenerator:
    """复盘报告生成器."""

    def __init__(self, game_log_path: str) -> None:
        self.calculator = MetricsCalculator(game_log_path)
        self.game_meta = self.calculator.game_meta
        self.rounds = self.calculator.rounds

    def generate(self) -> PostGameReport:
        """生成复盘报告."""
        report = PostGameReport(
            game_id=self.game_meta.get("game_id", ""),
            winner=self.game_meta.get("winner"),
            total_rounds=self.game_meta.get("total_rounds", 0),
        )

        # 1. 败因归因（针对失败方）
        report.key_mistakes = self._analyze_mistakes()

        # 2. 时间线
        report.timeline = self._build_timeline()

        # 3. 各玩家综合评分
        report.player_scores = self._calculate_player_scores()

        # 4. 关键决策点（影响力分析）
        report.pivotal_moments = self._find_pivotal_moments()

        return report

    def _analyze_mistakes(self) -> list[dict]:
        """分析失败方的关键失误."""
        mistakes = []
        players = self.game_meta.get("players", [])
        winner = self.game_meta.get("winner")

        # 找出失败方玩家
        losers = [
            p for p in players
            if ("werewolf" if p["role"] == "werewolf" else "good") != winner
        ]

        # 简化分析：检查是否有明显的决策失误
        for p in losers:
            pid = p["player_id"]
            role = p["role"]

            # 预言家未及时跳身份
            if role == "seer":
                seer_actions = [
                    a for rnd in self.rounds for a in rnd.get("actions", [])
                    if a.get("agent_id") == pid and a.get("action_type") == "check"
                ]
                if len(seer_actions) < 2:
                    mistakes.append({
                        "player_id": pid,
                        "role": role,
                        "mistake": "预言家查验次数过少，未能有效传递信息",
                        "severity": "high",
                    })

            # 女巫盲毒/盲救
            if role == "witch":
                witch_poison = [
                    a for rnd in self.rounds for a in rnd.get("actions", [])
                    if a.get("agent_id") == pid and a.get("action_type") == "poison"
                ]
                if witch_poison:
                    target = witch_poison[0].get("target_id")
                    target_role = next(
                        (pp["role"] for pp in players if pp["player_id"] == target),
                        None,
                    )
                    if target_role and target_role != "werewolf":
                        mistakes.append({
                            "player_id": pid,
                            "role": role,
                            "mistake": f"女巫毒了好人（{target}号，{target_role}）",
                            "severity": "high",
                        })

            # 狼人刀法
            if role == "werewolf":
                kills = [
                    a for rnd in self.rounds for a in rnd.get("actions", [])
                    if a.get("agent_id") == pid and a.get("action_type") == "kill"
                ]
                if kills:
                    # 检查是否一直在刀平民（效率低）
                    pass

        # 只取最重要的3个
        return mistakes[:3]

    def _build_timeline(self) -> list[dict]:
        """构建关键决策点时间线."""
        timeline = []
        for rnd in self.rounds:
            round_num = rnd.get("round_num", 0)
            phase = rnd.get("phase", "")
            for action in rnd.get("actions", []):
                if action.get("action_type") in ("kill", "check", "save", "poison", "shoot", "vote"):
                    timeline.append({
                        "round": round_num,
                        "phase": phase,
                        "agent_id": action.get("agent_id"),
                        "action": action.get("action_type"),
                        "target": action.get("target_id"),
                        "reasoning": action.get("reasoning", "")[:100],
                    })
        return timeline

    def _calculate_player_scores(self) -> dict[int, float]:
        """计算每个玩家的综合评分（0-100）."""
        outcome = self.calculator.compute_outcome_metrics()
        process = self.calculator.compute_process_metrics()

        scores = {}
        for pid, om in outcome.items():
            pm = process.get(pid)
            # 结果分 60% + 过程分 40%
            outcome_score = om.win_rate * 60 + (om.avg_survival_rounds / max(om.games_played * 5, 1)) * 10
            if om.role == Role.SEER:
                outcome_score += om.seer_check_accuracy * 15
            elif om.role == Role.WITCH:
                outcome_score += om.witch_save_success_rate * 10 + om.witch_poison_accuracy * 10
            elif om.role == Role.WEREWOLF:
                outcome_score += om.first_night_kill_accuracy * 10

            process_score = 0
            if pm:
                process_score = (
                    pm.avg_speech_quality * 3
                    + pm.vote_consistency_rate * 10
                    + pm.info_utilization_score * 10
                    + (pm.defense_quality / 10) * 5
                )

            scores[pid] = min(100, max(0, outcome_score + process_score))

        return scores

    def _find_pivotal_moments(self) -> list[dict]:
        """找出决定胜负的关键时刻."""
        pivotal = []
        players = self.game_meta.get("players", [])
        winner = self.game_meta.get("winner")

        # 检查是否存在关键投票（比如平票后的随机放逐是否改变了局势）
        for rnd in self.rounds:
            if rnd.get("phase") == "day_vote":
                votes = [
                    a for a in rnd.get("actions", [])
                    if a.get("action_type") == "vote" and a.get("target_id")
                ]
                if len(votes) > 0:
                    vote_counts = {}
                    for v in votes:
                        tid = v["target_id"]
                        vote_counts[tid] = vote_counts.get(tid, 0) + 1
                    if len(vote_counts) >= 2:
                        max_v = max(vote_counts.values())
                        candidates = [k for k, v in vote_counts.items() if v == max_v]
                        if len(candidates) > 1:
                            pivotal.append({
                                "round": rnd["round_num"],
                                "event": "平票随机放逐",
                                "description": f"{candidates} 平票，随机放逐可能改变局势",
                            })

        return pivotal


# 避免循环导入的问题
from app.models.enums import Role
