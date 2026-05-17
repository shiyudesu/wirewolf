"""评测指标计算 — 结果指标 + 过程指标."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.models.enums import Role, Team, ActionType


@dataclass
class AgentOutcomeMetrics:
    """单个Agent在一局或多局中的结果指标."""

    agent_id: int
    role: Role
    games_played: int = 0
    wins: int = 0
    # 基础胜率
    win_rate: float = 0.0
    # 存活
    survival_rounds_total: int = 0
    avg_survival_rounds: float = 0.0
    # 被投票出局次数
    voted_out_count: int = 0
    vote_out_rate: float = 0.0
    # 狼人专属
    first_night_kills: int = 0
    first_night_kill_accuracy: float = 0.0  # 首刀命中神职/预言家率
    # 预言家专属
    seer_checks_total: int = 0
    seer_checks_correct: int = 0
    seer_check_accuracy: float = 0.0
    # 女巫专属
    witch_saves_total: int = 0
    witch_saves_successful: int = 0  # 救了好人
    witch_save_success_rate: float = 0.0
    witch_poison_total: int = 0
    witch_poison_correct: int = 0  # 毒了狼人
    witch_poison_accuracy: float = 0.0


@dataclass
class AgentProcessMetrics:
    """单个Agent的过程指标（单局）."""

    agent_id: int
    # 发言质量（1-10，LLM-as-a-Judge 或规则评分）
    speech_quality_scores: list[float] = field(default_factory=list)
    avg_speech_quality: float = 0.0
    # 投票一致性（言行一致，0-1）
    vote_consistency_rate: float = 0.0  # 投票目标是否与公开表态一致
    # 信息利用度（0-1）
    info_utilization_score: float = 0.0  # 是否充分利用已知信息
    # 辩护质量（被抗推时，1-10）
    defense_quality: float = 0.0


@dataclass
class GameMetrics:
    """单局游戏的完整评测结果."""

    game_id: str
    winner: Optional[str]
    total_rounds: int
    player_metrics: dict[int, AgentOutcomeMetrics] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 规则-based 过程指标辅助函数
# --------------------------------------------------------------------------- #

_LOGIC_KEYWORDS = [
    "因为", "所以", "因此", "如果", "那么", "但是", "然而", "不过",
    "首先", "其次", "最后", "总结", "推理", "逻辑", "证明", "说明",
    "既然", "除非", "否则", "虽然", "尽管", "可能", "也许", "一定",
    "since", "because", "therefore", "however", "but", "if", "then",
    "so", "thus", "although", "unless", "maybe", "probably", "must",
]

_DEFENSE_KEYWORDS = [
    "我是", "我不是", "好人", "冤枉", "抗推", "金水", "银水",
    "证明", "验我", "投我", "错了", "保我", "相信我",
]


def _score_speech_rule_based(speech: str, role: str) -> float:
    """基于规则计算单条发言质量（1-10）."""
    if not speech or len(speech) < 5:
        return 2.0

    score = 5.0  # 基础分

    # 长度惩罚/奖励（过短或过长都不好）
    length = len(speech)
    if length < 20:
        score -= 2.0
    elif length < 50:
        score -= 1.0
    elif 50 <= length <= 300:
        score += 1.0
    elif length > 600:
        score -= 0.5  # 过于冗长

    # 逻辑连接词密度奖励
    logic_count = sum(1 for kw in _LOGIC_KEYWORDS if kw in speech)
    score += min(logic_count * 0.4, 2.0)

    # 玩家 ID 引用（信息密度）
    id_refs = len(re.findall(r"(\d+)号", speech))
    score += min(id_refs * 0.3, 1.5)

    # 角色提及（信息密度）
    role_refs = len(re.findall(r"(狼人|好人|神职|平民|预言家|女巫|猎人)", speech))
    score += min(role_refs * 0.3, 1.0)

    # 狼人额外：伪装度评估（是否避免暴露狼相关词汇）
    if role == "werewolf":
        wolf_exposure = sum(1 for kw in ["刀", "杀队友", "我们狼", "晚上"] if kw in speech)
        score -= wolf_exposure * 1.5

    return max(1.0, min(10.0, score))


def _extract_mentioned_targets(speech: str) -> set[int]:
    """从发言中提取被提及的玩家 ID."""
    matches = re.findall(r"(\d+)号", speech)
    return {int(m) for m in matches}


def _compute_vote_consistency(speeches: list[str], votes: list[int]) -> float:
    """计算投票一致性：发言中提及的目标与实际投票的一致性."""
    if not votes:
        return 0.0

    consistent = 0
    for i, vote in enumerate(votes):
        # 获取该投票前的所有发言
        prior_speeches = speeches[: i + 1] if i < len(speeches) else speeches
        mentioned = set()
        for s in prior_speeches:
            mentioned |= _extract_mentioned_targets(s)

        if vote in mentioned:
            consistent += 1
        elif len(mentioned) == 0:
            # 从未提任何人，视为中立
            consistent += 0.5

    return consistent / len(votes)


def _compute_info_utilization(
    speeches: list[str],
    private_info_checks: list[str],
    role: str,
    agent_results: list[dict] = None,
) -> float:
    """计算信息利用度：私有信息是否在发言中被引用."""
    if not speeches:
        return 0.0

    agent_results = agent_results or []
    # 收集发言中提到的所有数字和关键词
    mentioned_ids = set()
    all_text = " ".join(speeches)
    for s in speeches:
        mentioned_ids |= _extract_mentioned_targets(s)

    utilized = 0
    total_info = 0

    if role == "seer" and private_info_checks:
        # 查验结果中提到的玩家 ID 及其结果
        for check in private_info_checks:
            matches = re.findall(r"(\d+)号", check)
            result = "werewolf" if "werewolf" in check or "狼人" in check else "good"
            for m in matches:
                total_info += 1
                mid = int(m)
                if mid in mentioned_ids:
                    # 不仅提到 ID，还要提到查验结果（好人/狼人）
                    if (result == "werewolf" and any(k in all_text for k in [f"{mid}号狼", f"{mid}号是狼", f"{mid}号 狼"])) or \
                       (result == "good" and any(k in all_text for k in [f"{mid}号好", f"{mid}号金", f"{mid}号是好人"])):
                        utilized += 1

    elif role == "witch":
        # 女巫：检查是否提到刀口/银水/救毒逻辑
        total_info = 1
        if any(kw in all_text for kw in ["银水", "刀口", "救", "毒"]):
            # 进一步检查是否有逻辑推理
            if any(kw in all_text for kw in ["因为", "所以", "如果", "那么"]):
                utilized = 1

    elif role == "werewolf":
        # 狼人：检查是否引用了刀法逻辑或队友协商
        total_info = 1
        if any(kw in all_text for kw in ["刀", "杀", "队友", "抗推", "做身份"]):
            utilized = 1

    elif role in ("hunter", "villager"):
        # 猎人/平民：检查是否利用公开投票信息
        total_info = 1
        if any(kw in all_text for kw in ["投票", "票型", "放逐", "上轮"]):
            utilized = 1

    if total_info == 0:
        return 0.5

    return min(1.0, utilized / total_info)


def _score_defense_rule_based(speech: str) -> float:
    """评估单条辩护发言质量（1-10）."""
    if not speech:
        return 1.0

    score = 5.0
    length = len(speech)
    if length < 10:
        score -= 2.0
    elif length >= 30:
        score += 1.0

    # 辩护关键词
    defense_count = sum(1 for kw in _DEFENSE_KEYWORDS if kw in speech)
    score += min(defense_count * 0.5, 2.5)

    # 逻辑词
    logic_count = sum(1 for kw in _LOGIC_KEYWORDS if kw in speech)
    score += min(logic_count * 0.3, 1.5)

    return max(1.0, min(10.0, score))


class MetricsCalculator:
    """从游戏日志中计算各类指标."""

    def __init__(self, game_log_path: str) -> None:
        self.game_log_path = game_log_path
        self.game_meta: dict = {}
        self.rounds: list[dict] = []
        self._load()

    def _load(self) -> None:
        with open(self.game_log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines:
            self.game_meta = json.loads(lines[0])
            self.rounds = []
            for line in lines[1:]:
                obj = json.loads(line)
                # 跳过 agent_decisions 等非轮次日志
                if isinstance(obj, dict) and obj.get("type") != "agent_decisions" and "round_num" in obj:
                    self.rounds.append(obj)

    def compute_outcome_metrics(self) -> dict[int, AgentOutcomeMetrics]:
        """计算结果指标."""
        players = self.game_meta.get("players", [])
        winner = self.game_meta.get("winner")
        total_rounds = self.game_meta.get("total_rounds", 0)

        metrics: dict[int, AgentOutcomeMetrics] = {}

        # 初始化
        for p in players:
            pid = p["player_id"]
            role = Role(p["role"])
            metrics[pid] = AgentOutcomeMetrics(agent_id=pid, role=role)
            metrics[pid].games_played = 1

        # 胜负
        for p in players:
            pid = p["player_id"]
            team = "werewolf" if p["role"] == "werewolf" else "good"
            if team == winner:
                metrics[pid].wins = 1
            metrics[pid].win_rate = 1.0 if team == winner else 0.0

        # 存活轮数（简化：死亡轮次 = 最后出现的轮次 + 1）
        death_rounds: dict[int, int] = {}
        for rnd in self.rounds:
            for death in rnd.get("deaths", []):
                if death not in death_rounds:
                    death_rounds[death] = rnd["round_num"]

        for p in players:
            pid = p["player_id"]
            if p["alive"]:
                metrics[pid].survival_rounds_total = total_rounds
            else:
                metrics[pid].survival_rounds_total = death_rounds.get(pid, 0)
            metrics[pid].avg_survival_rounds = float(metrics[pid].survival_rounds_total)

            # 被投票出局（在 day_execution 阶段死亡且原因包含 vote）
            if pid in death_rounds:
                death_round = death_rounds[pid]
                for rnd in self.rounds:
                    if rnd["round_num"] == death_round and rnd.get("phase") == "day_execution":
                        metrics[pid].voted_out_count = 1
                        break
                metrics[pid].vote_out_rate = float(metrics[pid].voted_out_count)

        # 角色专属指标（简化版）
        self._compute_role_specific(metrics, players)

        return metrics

    def _compute_role_specific(
        self, metrics: dict[int, AgentOutcomeMetrics], players: list[dict]
    ) -> None:
        """计算角色专属指标."""
        player_roles = {p["player_id"]: p["role"] for p in players}

        # 狼人首刀命中率：只看第一晚最终执行的击杀目标
        first_round_werewolf = next(
            (rnd for rnd in self.rounds if rnd.get("round_num") == 0),
            None,
        )
        if first_round_werewolf:
            # 从 system message 中读取最终击杀目标
            final_targets = []
            for msg in first_round_werewolf.get("messages", []):
                if msg.get("msg_type") == "system" and "最终决定击杀" in msg.get("content", ""):
                    match = re.search(r"最终决定击杀 (\d+)号", msg["content"])
                    if match:
                        final_targets.append(int(match.group(1)))
            # 如果没有 system message，从 action results 推断
            if not final_targets:
                for result in first_round_werewolf.get("results", []):
                    action = result.get("action", {})
                    if action.get("action_type") == "kill":
                        target = action.get("target_id")
                        if target:
                            final_targets.append(target)
            for target in set(final_targets):
                target_role = player_roles.get(target)
                # 给所有狼人共享首刀命中结果（团队指标）
                for agent_id, m in metrics.items():
                    if m.role == Role.WEREWOLF:
                        m.first_night_kills = 1
                        if target_role and target_role in ("seer", "witch", "hunter"):
                            m.first_night_kill_accuracy = 1.0

        # 预言家验人准确率：从 action results 中读取查验结果
        check_results: dict[int, list[tuple[int, str, str]]] = {}  # agent_id -> [(target, reported_result, actual)]
        for rnd in self.rounds:
            for result in rnd.get("results", []):
                action = result.get("action", {})
                if action.get("action_type") == "check":
                    agent_id = action.get("agent_id")
                    target = action.get("target_id")
                    if agent_id and target:
                        actual = "werewolf" if player_roles.get(target) == "werewolf" else "good"
                        # result message 包含 "werewolf" 或 "good"
                        reported = result.get("message", "")
                        reported_result = "werewolf" if "werewolf" in reported else "good"
                        if agent_id not in check_results:
                            check_results[agent_id] = []
                        check_results[agent_id].append((target, reported_result, actual))

        for agent_id, checks in check_results.items():
            if agent_id in metrics:
                metrics[agent_id].seer_checks_total = len(checks)
                correct = sum(1 for _, reported, actual in checks if reported == actual)
                metrics[agent_id].seer_checks_correct = correct
                metrics[agent_id].seer_check_accuracy = correct / len(checks) if checks else 0.0

        # 女巫指标：从 action results 读取
        for rnd in self.rounds:
            for result in rnd.get("results", []):
                action = result.get("action", {})
                agent_id = action.get("agent_id")
                if not agent_id or agent_id not in metrics:
                    continue
                if action.get("action_type") == "save":
                    metrics[agent_id].witch_saves_total += 1
                    msg = result.get("message", "")
                    # 成功救下且目标为好人（或自身第一夜）才算成功
                    if "成功救下" in msg:
                        # 提取救下的目标
                        match = re.search(r"成功救下 (\d+)号", msg)
                        if match:
                            saved_target = int(match.group(1))
                            target_role = player_roles.get(saved_target)
                            if target_role and target_role != "werewolf":
                                metrics[agent_id].witch_saves_successful += 1
                elif action.get("action_type") == "poison":
                    metrics[agent_id].witch_poison_total += 1
                    target = action.get("target_id")
                    if target and player_roles.get(target) == "werewolf":
                        metrics[agent_id].witch_poison_correct += 1

        # 计算比率
        for m in metrics.values():
            if m.first_night_kills > 0:
                m.first_night_kill_accuracy = m.first_night_kill_accuracy / m.first_night_kills
            if m.witch_saves_total > 0:
                m.witch_save_success_rate = m.witch_saves_successful / m.witch_saves_total
            if m.witch_poison_total > 0:
                m.witch_poison_accuracy = m.witch_poison_correct / m.witch_poison_total

    # ------------------------------------------------------------------ #
    # 过程指标 — 规则-based + 可选 LLM-as-a-Judge
    # ------------------------------------------------------------------ #

    def compute_process_metrics(self) -> dict[int, AgentProcessMetrics]:
        """计算过程指标（规则-based，同步方法）."""
        return self._compute_process_metrics_core(use_llm=False)

    async def compute_process_metrics_async(
        self,
        llm_judge=None,
    ) -> dict[int, AgentProcessMetrics]:
        """计算过程指标（异步，可选接入 LLM-as-a-Judge）.

        Args:
            llm_judge: LLMJudge 实例，为 None 则只用规则评分。
        """
        metrics = self._compute_process_metrics_core(use_llm=False)

        if llm_judge is None:
            return metrics

        # 使用 LLM 对关键发言进行评分
        import asyncio

        players = self.game_meta.get("players", [])
        player_roles = {p["player_id"]: p["role"] for p in players}

        # 收集需要 LLM 评分的数据
        speech_tasks = []
        defense_tasks = []
        speech_map = []  # (agent_id, index)
        defense_map = []  # (agent_id, speech)

        for agent_id, m in metrics.items():
            role = player_roles.get(agent_id, "unknown")

            # 收集该 agent 的所有发言
            agent_speeches = []
            for rnd in self.rounds:
                for action in rnd.get("actions", []):
                    if action.get("agent_id") == agent_id and action.get("action_type") == "speak":
                        content = action.get("content", "")
                        if content:
                            agent_speeches.append(content)

            # 批量创建 LLM 评分任务
            for idx, speech in enumerate(agent_speeches):
                context = f"第{idx+1}轮白天发言阶段，{role}玩家"
                speech_tasks.append(
                    llm_judge.judge_speech(
                        speaker_role=role,
                        speech=speech,
                        context=context,
                    )
                )
                speech_map.append((agent_id, idx))

            # 检查该 agent 是否被放逐（需要辩护评分）
            for rnd in self.rounds:
                if rnd.get("phase") == "day_execution":
                    for action in rnd.get("actions", []):
                        if action.get("agent_id") == agent_id and action.get("action_type") == "speak":
                            content = action.get("content", "")
                            if content:
                                defense_tasks.append(
                                    llm_judge.judge_defense(
                                        speech=content,
                                        situation=f"第{rnd['round_num']}轮被投票放逐",
                                    )
                                )
                                defense_map.append((agent_id, content))

        # 并发执行 LLM 评分
        if speech_tasks:
            speech_results = await asyncio.gather(*speech_tasks, return_exceptions=True)
            for (agent_id, idx), result in zip(speech_map, speech_results):
                if isinstance(result, Exception):
                    continue
                # 取各维度平均分
                avg_score = sum(result.values()) / max(len(result), 1)
                # 更新对应 agent 的评分（替换规则评分）
                if agent_id in metrics:
                    # 将对应位置的发言质量替换为 LLM 评分
                    if metrics[agent_id].speech_quality_scores:
                        if idx < len(metrics[agent_id].speech_quality_scores):
                            metrics[agent_id].speech_quality_scores[idx] = avg_score
                    else:
                        metrics[agent_id].speech_quality_scores.append(avg_score)

        if defense_tasks:
            defense_results = await asyncio.gather(*defense_tasks, return_exceptions=True)
            for (agent_id, _), result in zip(defense_map, defense_results):
                if isinstance(result, Exception):
                    continue
                if agent_id in metrics:
                    metrics[agent_id].defense_quality = result

        # 重新计算平均分
        for m in metrics.values():
            if m.speech_quality_scores:
                m.avg_speech_quality = sum(m.speech_quality_scores) / len(m.speech_quality_scores)

        return metrics

    def _compute_process_metrics_core(self, use_llm: bool = False) -> dict[int, AgentProcessMetrics]:
        """过程指标核心计算（规则-based）."""
        metrics: dict[int, AgentProcessMetrics] = {}
        players = self.game_meta.get("players", [])
        player_roles = {p["player_id"]: p["role"] for p in players}

        # 按 agent 收集发言和投票
        speeches: dict[int, list[str]] = {}
        votes: dict[int, list[int]] = {}
        private_checks: dict[int, list[str]] = {}  # 预言家查验记录
        death_rounds: dict[int, int] = {}

        for rnd in self.rounds:
            for death in rnd.get("deaths", []):
                if death not in death_rounds:
                    death_rounds[death] = rnd["round_num"]

            for action in rnd.get("actions", []):
                agent_id = action.get("agent_id")
                if agent_id is None:
                    continue
                if agent_id not in metrics:
                    metrics[agent_id] = AgentProcessMetrics(agent_id=agent_id)

                if action.get("action_type") == "speak" and action.get("content"):
                    if agent_id not in speeches:
                        speeches[agent_id] = []
                    speeches[agent_id].append(action["content"])

                if action.get("action_type") == "vote" and action.get("target_id"):
                    if agent_id not in votes:
                        votes[agent_id] = []
                    votes[agent_id].append(action["target_id"])

                # 收集预言家查验信息
                if action.get("action_type") == "check" and action.get("private_info"):
                    if agent_id not in private_checks:
                        private_checks[agent_id] = []
                    private_checks[agent_id].append(action.get("private_info", ""))

        # 计算每个 agent 的过程指标
        for agent_id, m in metrics.items():
            role = player_roles.get(agent_id, "unknown")
            agent_speeches = speeches.get(agent_id, [])
            agent_votes = votes.get(agent_id, [])

            # 1. 发言质量（规则-based）
            m.speech_quality_scores = [
                _score_speech_rule_based(s, role) for s in agent_speeches
            ]
            if m.speech_quality_scores:
                m.avg_speech_quality = sum(m.speech_quality_scores) / len(m.speech_quality_scores)
            else:
                m.avg_speech_quality = 3.0  # 从未发言，默认较低

            # 2. 投票一致性
            m.vote_consistency_rate = _compute_vote_consistency(agent_speeches, agent_votes)

            # 3. 信息利用度
            agent_results = []
            for rnd in self.rounds:
                agent_results.extend([r for r in rnd.get("results", []) if r.get("action", {}).get("agent_id") == agent_id])
            m.info_utilization_score = _compute_info_utilization(
                agent_speeches,
                private_checks.get(agent_id, []),
                role,
                agent_results,
            )

            # 4. 辩护质量（被放逐时的发言）
            defense_speeches = []
            for rnd in self.rounds:
                if rnd.get("phase") == "day_execution":
                    for action in rnd.get("actions", []):
                        if action.get("agent_id") == agent_id and action.get("action_type") == "speak":
                            content = action.get("content", "")
                            if content:
                                defense_speeches.append(content)

            if defense_speeches:
                m.defense_quality = sum(
                    _score_defense_rule_based(s) for s in defense_speeches
                ) / len(defense_speeches)
            else:
                m.defense_quality = 5.0

        return metrics
