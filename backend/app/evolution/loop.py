"""进化循环 — 批量对局 → 评测 → 优化 → 再对局."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from typing import Optional

from app.llm.client import LLMClient
from app.llm.mock_client import MockLLMClient
from app.models.game import GameConfig
from app.models.log import AgentProfile
from app.engine.game_master import GameMaster
import uuid
from app.evaluation.leaderboard import LeaderboardDB
from app.evaluation.metrics import MetricsCalculator
from app.evaluation.report import ReportGenerator
from app.evolution.optimizer import StrategyOptimizer
from app.evolution.guard import DegenerationGuard, GuardResult


@dataclass
class EvolutionConfig:
    """进化循环配置."""

    generations: int = 5  # 进化代数
    games_per_generation: int = 10  # 每代对局数
    min_games_for_eval: int = 5  # 用于评估的最少局数
    target_metric: str = "win_rate"
    use_mock: bool = False
    pass  # db 连接由环境变量 DATABASE_URL 控制


@dataclass
class EvolutionResult:
    """进化循环结果."""

    generation: int
    agent_id: int
    role: str
    old_version: int
    new_version: int
    old_metrics: dict[str, float]
    new_metrics: dict[str, float]
    guard_result: GuardResult
    accepted: bool


class EvolutionLoop:
    """自进化主循环."""

    def __init__(
        self,
        game_config: GameConfig,
        evo_config: EvolutionConfig,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.game_config = game_config
        self.evo_config = evo_config
        self.llm = llm_client or (MockLLMClient() if evo_config.use_mock else LLMClient())
        self.db = LeaderboardDB()
        self.optimizer = StrategyOptimizer(llm_client=self.llm, db=self.db)
        self.guard = DegenerationGuard(llm_client=self.llm)

        # 跟踪各 Agent 的版本历史
        self.version_history: dict[str, list[dict]] = {}  # agent_profile_id -> [{version, score}]
        # 按角色存储的 Profile（核心：角色 -> 最佳 Profile）
        self.role_profiles: dict[str, AgentProfile] = {}

        # 从数据库加载历史 profile
        # 注意：异步初始化由调用方在 run() 中完成
        self._profiles_loaded = False

    async def run(self) -> list[EvolutionResult]:
        """运行完整进化循环."""
        all_results: list[EvolutionResult] = []

        # 第一代：基线对局（使用默认策略）
        print(f"\n{'='*60}")
        print("进化循环启动")
        print(f"  每代对局: {self.evo_config.games_per_generation}")
        print(f"  进化代数: {self.evo_config.generations}")
        print(f"{'='*60}")

        # 异步初始化：建表 + 加载 profile
        await self.db.init_db()
        await self._load_profiles_from_db()

        # 先运行第一代基线
        baseline_game_ids = await self._run_generation(0)
        print(f"\n基线对局完成，游戏ID: {[g[:8] for g in baseline_game_ids]}")

        for gen in range(1, self.evo_config.generations + 1):
            print(f"\n{'='*60}")
            print(f"第 {gen}/{self.evo_config.generations} 代进化")
            print(f"{'='*60}")

            # 1. 选择需要优化的 Agent（按角色表现选择）
            agents_to_optimize = await self._select_agents_for_optimization(baseline_game_ids)

            # 2. 对每个 Agent 执行优化
            new_profiles: dict[int, AgentProfile] = {}
            new_role_profiles: dict[str, AgentProfile] = {}
            for agent_id, role, current_profile in agents_to_optimize:
                print(f"\n--- 优化 Agent {agent_id} ({role}) v{current_profile.version} ---")

                # 获取历史表现
                old_metrics = await self._get_agent_metrics(agent_id, baseline_game_ids[-self.evo_config.min_games_for_eval:])

                # 生成新策略
                new_profile = await self.optimizer.optimize(
                    agent_id=agent_id,
                    role=role,
                    current_profile=current_profile,
                    recent_game_ids=baseline_game_ids[-self.evo_config.min_games_for_eval:],
                    target_metric=self.evo_config.target_metric,
                )

                # LLM 自审
                guard_llm = await self.guard.llm_self_review(current_profile, new_profile)
                if not guard_llm.approved:
                    print(f"  LLM 自审未通过: {guard_llm.reason}")
                    new_profile = current_profile

                new_profiles[agent_id] = new_profile
                new_role_profiles[role] = new_profile
                # 持久化到数据库
                await self.db.save_profile(
                    agent_profile_id=new_profile.agent_profile_id or str(uuid.uuid4()),
                    role=role,
                    version=new_profile.version,
                    notes=new_profile.strategy_notes,
                    model_name=new_profile.model_name,
                )

            # 更新角色级 profile
            self.role_profiles.update(new_role_profiles)

            # 3. 用新策略运行对局
            new_game_ids = await self._run_generation(gen)

            # 4. 评估新策略效果
            for agent_id, role, old_profile in agents_to_optimize:
                new_profile = new_profiles.get(agent_id, old_profile)
                if new_profile.version == old_profile.version:
                    continue  # 未更新，跳过

                new_metrics = await self._get_agent_metrics(agent_id, new_game_ids)
                old_metrics = await self._get_agent_metrics(agent_id, baseline_game_ids[-self.evo_config.min_games_for_eval:])

                # 指标防护检查
                guard_metric = self.guard.check_metrics(old_metrics, new_metrics)

                accepted = guard_metric.approved

                profile_id = new_profile.agent_profile_id or str(agent_id)
                # 检查是否需要回滚
                if profile_id not in self.version_history:
                    self.version_history[profile_id] = []
                self.version_history[profile_id].append({
                    "version": new_profile.version,
                    "score": new_metrics.get("avg_score", 0),
                })

                if self.guard.should_rollback(self.version_history[profile_id]):
                    print(f"  ⚠️ Agent {agent_id} 连续退化，建议回滚到 v{old_profile.version}")
                    accepted = False
                    # 回滚
                    self.role_profiles[role] = old_profile

                result = EvolutionResult(
                    generation=gen,
                    agent_id=agent_id,
                    role=role,
                    old_version=old_profile.version,
                    new_version=new_profile.version,
                    old_metrics=old_metrics,
                    new_metrics=new_metrics,
                    guard_result=guard_metric,
                    accepted=accepted,
                )
                all_results.append(result)

                status = "✅ 接受" if accepted else "❌ 拒绝"
                print(f"  {status} 新版本 v{new_profile.version}")
                print(f"     胜率: {old_metrics.get('win_rate', 0):.1%} -> {new_metrics.get('win_rate', 0):.1%}")
                print(f"     评分: {old_metrics.get('avg_score', 0):.1f} -> {new_metrics.get('avg_score', 0):.1f}")

            # 更新基线
            baseline_game_ids = new_game_ids

        return all_results

    async def _run_generation(self, generation: int) -> list[str]:
        """运行一代对局，返回游戏ID列表."""
        game_ids = []
        for i in range(self.evo_config.games_per_generation):
            gm = GameMaster(
                config=self.game_config,
                llm_client=self.llm,
            )

            # 先初始化游戏（分配角色）
            await gm.setup()

            # 注入当前进化中的 profile（按角色匹配）
            for pid, agent in gm.agents.items():
                role = agent.role.value
                if role in self.role_profiles:
                    agent.profile = copy.deepcopy(self.role_profiles[role])

            # 运行对局
            await gm.run()
            game_ids.append(gm.game_id)

            # 入库
            await self.db.record_game(
                game_id=gm.game_id,
                config=self.game_config.model_dump(),
                winner=gm.game_state.winner.value if gm.game_state.winner else None,
                total_rounds=gm.game_state.round_num,
            )

            # 计算指标并入库
            calculator = MetricsCalculator(gm.log_file)
            outcome = calculator.compute_outcome_metrics()
            process = calculator.compute_process_metrics()
            report_gen = ReportGenerator(gm.log_file)
            report = report_gen.generate()

            # 触发局后反思
            try:
                await gm.post_game_reflection()
            except Exception as e:
                print(f"  局后反思失败: {e}")

            for pid, om in outcome.items():
                pm = process.get(pid)
                score = report.player_scores.get(pid, 0.0)
                agent = gm.agents.get(pid)
                version = agent.profile.version if agent else 1
                model_name = agent.profile.model_name if agent else ""
                await self.db.record_player_stats(
                    game_id=gm.game_id,
                    outcome=om,
                    process=pm,
                    overall_score=score,
                    strategy_version=version,
                    model_name=model_name,
                )

        return game_ids

    async def _load_profiles_from_db(self) -> None:
        """从数据库加载最新 profile 到 role_profiles."""
        try:
            db_profiles = await self.db.load_latest_profiles()
            for (profile_id, role), data in db_profiles.items():
                profile = AgentProfile(
                    role_description=data.get("role", ""),
                    strategy_notes=data.get("strategy_notes", ""),
                    version=data.get("strategy_version", 1),
                    agent_profile_id=profile_id,
                    model_name=data.get("model_name", ""),
                )
                self.role_profiles[role] = profile
        except Exception as e:
            print(f"  从数据库加载 profile 失败: {e}")

    async def _select_agents_for_optimization(
        self,
        recent_game_ids: list[str],
    ) -> list[tuple[int, str, AgentProfile]]:
        """选择需要优化的 Agent 列表.

        策略：从最近对局中查询各角色的平均表现，
        选择表现最差的角色对应的 Agent 进行优化。
        """
        if not recent_game_ids:
            return []

        rows = await self.db.get_role_performance(recent_game_ids)
        if not rows:
            return []

        results = []
        for r in rows:
            role = r["role"]
            agent_id = r["agent_id"]
            profile = self.role_profiles.get(role)
            if profile is None:
                profile = AgentProfile(role_description="")
            results.append((agent_id, role, profile))

        return results

    async def _get_agent_metrics(self, agent_id: int, game_ids: list[str]) -> dict[str, float]:
        """获取 Agent 在指定对局中的平均指标."""
        return await self.db.get_agent_metrics(agent_id, game_ids)
