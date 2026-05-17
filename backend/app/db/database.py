"""异步数据库访问层 — PostgreSQL 版 LeaderboardDB."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import async_session_maker, engine
from app.db.models import AgentProfileModel, Game, PlayerStat
from app.evaluation.metrics import AgentOutcomeMetrics, AgentProcessMetrics


class AsyncLeaderboardDB:
    """排行榜异步数据库（PostgreSQL）."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    async def init_db(self) -> None:
        """建表（安全幂等，不会删已有数据）."""
        from app.db.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ------------------------------------------------------------------ #
    # 写操作
    # ------------------------------------------------------------------ #

    async def record_game(
        self,
        game_id: str,
        config: dict,
        winner: Optional[str],
        total_rounds: int,
    ) -> None:
        async with async_session_maker() as session:
            game = Game(
                game_id=game_id,
                config=config,
                winner=winner,
                total_rounds=total_rounds,
            )
            await session.merge(game)
            await session.commit()

    async def record_player_stats(
        self,
        game_id: str,
        outcome: AgentOutcomeMetrics,
        process: Optional[AgentProcessMetrics] = None,
        overall_score: float = 0.0,
        strategy_version: int = 1,
        model_name: str = "",
    ) -> None:
        async with async_session_maker() as session:
            stat = PlayerStat(
                game_id=game_id,
                agent_id=outcome.agent_id,
                role=outcome.role.value,
                won=1 if outcome.wins > 0 else 0,
                survival_rounds=outcome.survival_rounds_total,
                win_rate=outcome.win_rate,
                seer_check_accuracy=outcome.seer_check_accuracy,
                witch_save_rate=outcome.witch_save_success_rate,
                witch_poison_accuracy=outcome.witch_poison_accuracy,
                first_night_kill_accuracy=outcome.first_night_kill_accuracy,
                speech_quality=process.avg_speech_quality if process else 0.0,
                overall_score=overall_score,
                strategy_version=strategy_version,
                info_utilization_score=process.info_utilization_score if process else 0.0,
                defense_quality=process.defense_quality if process else 0.0,
                vote_consistency_rate=process.vote_consistency_rate if process else 0.0,
                model_name=model_name,
            )
            session.add(stat)
            await session.commit()

    async def save_profile(
        self,
        agent_profile_id: str,
        role: str,
        version: int,
        notes: str,
        model_name: str = "",
    ) -> None:
        async with async_session_maker() as session:
            profile = AgentProfileModel(
                agent_profile_id=agent_profile_id,
                role=role,
                strategy_version=version,
                strategy_notes=notes,
                model_name=model_name,
                created_at=datetime.utcnow(),
            )
            await session.merge(profile)
            await session.commit()

    # ------------------------------------------------------------------ #
    # 读操作
    # ------------------------------------------------------------------ #

    async def get_leaderboard(
        self,
        role: Optional[str] = None,
        model_name: Optional[str] = None,
        min_games: int = 3,
        limit: int = 20,
    ) -> list[dict]:
        async with async_session_maker() as session:
            # 使用原生 SQL 保持和旧版一致的聚合逻辑
            conditions = []
            params: dict = {}
            if role:
                conditions.append("role = :role")
                params["role"] = role
            if model_name:
                conditions.append("model_name = :model_name")
                params["model_name"] = model_name

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            query = text(f"""
                SELECT
                    role,
                    strategy_version,
                    model_name,
                    COUNT(*) as games,
                    AVG(win_rate) as avg_win_rate,
                    AVG(overall_score) as avg_score,
                    AVG(survival_rounds) as avg_survival,
                    AVG(info_utilization_score) as avg_info_utilization,
                    AVG(defense_quality) as avg_defense_quality
                FROM player_stats
                {where_clause}
                GROUP BY role, strategy_version, model_name
                HAVING COUNT(*) >= :min_games
                ORDER BY avg_score DESC
                LIMIT :limit
            """)
            params.update(min_games=min_games, limit=limit)
            result = await session.execute(query, params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def list_games(self, limit: int = 50) -> list[dict]:
        """列出最近的游戏."""
        async with async_session_maker() as session:
            result = await session.execute(
                text("SELECT * FROM games ORDER BY played_at DESC LIMIT :limit"),
                {"limit": limit},
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def get_game_stats(self) -> dict:
        """替代 routes.py /batch/status 中的原始查询."""
        async with async_session_maker() as session:
            total_result = await session.execute(
                text("SELECT COUNT(*) FROM games")
            )
            total_games = total_result.scalar() or 0

            wins_result = await session.execute(
                text("SELECT winner, COUNT(*) FROM games GROUP BY winner")
            )
            wins = {row[0]: row[1] for row in wins_result.all()}

            return {
                "total_games": total_games,
                "werewolf_wins": wins.get("werewolf", 0),
                "good_wins": wins.get("good", 0),
            }

    async def get_agent_evolution(self, agent_id: int) -> list[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                text("""
                    SELECT strategy_version, role, model_name,
                           AVG(win_rate) as win_rate, AVG(overall_score) as score,
                           AVG(info_utilization_score) as info_utilization,
                           AVG(defense_quality) as defense_quality,
                           COUNT(*) as games
                    FROM player_stats
                    WHERE agent_id = :agent_id
                    GROUP BY strategy_version, role, model_name
                    ORDER BY strategy_version
                """),
                {"agent_id": agent_id},
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def load_latest_profiles(self) -> dict[tuple[str, str], dict]:
        async with async_session_maker() as session:
            # 子查询取每个 (profile_id, role) 的最新版本
            result = await session.execute(
                text("""
                    SELECT agent_profile_id, role, strategy_version,
                           strategy_notes, model_name
                    FROM agent_profiles ap
                    WHERE strategy_version = (
                        SELECT MAX(strategy_version)
                        FROM agent_profiles
                        WHERE agent_profile_id = ap.agent_profile_id
                          AND role = ap.role
                    )
                """)
            )
            rows = result.mappings().all()
            result_dict = {}
            for r in rows:
                key = (r["agent_profile_id"], r["role"])
                result_dict[key] = dict(r)
            return result_dict

    # ------------------------------------------------------------------ #
    # 进化循环专用查询
    # ------------------------------------------------------------------ #

    async def get_agent_performance(
        self,
        agent_id: int,
        game_ids: list[str],
    ) -> dict:
        """替代 optimizer._collect_performance."""
        if not game_ids:
            return {"games": 0, "avg_win_rate": 0, "avg_score": 0}

        async with async_session_maker() as session:
            placeholders = ",".join(f":gid{i}" for i in range(len(game_ids)))
            params = {f"gid{i}": gid for i, gid in enumerate(game_ids)}
            params["agent_id"] = agent_id

            result = await session.execute(
                text(f"""
                    SELECT * FROM player_stats
                    WHERE agent_id = :agent_id AND game_id IN ({placeholders})
                    ORDER BY game_id
                """),
                params,
            )
            rows = result.mappings().all()
            if not rows:
                return {"games": 0, "avg_win_rate": 0, "avg_score": 0}

            total = len(rows)
            wins = sum(1 for r in rows if r["won"])
            avg_score = sum(r["overall_score"] for r in rows) / total
            avg_survival = sum(r["survival_rounds"] for r in rows) / total
            return {
                "games": total,
                "wins": wins,
                "win_rate": wins / total,
                "avg_score": avg_score,
                "avg_survival": avg_survival,
                "details": [dict(r) for r in rows],
            }

    async def get_role_performance(
        self,
        game_ids: list[str],
    ) -> list[dict]:
        """替代 loop._select_agents_for_optimization 的查询."""
        if not game_ids:
            return []

        async with async_session_maker() as session:
            placeholders = ",".join(f":gid{i}" for i in range(len(game_ids)))
            params = {f"gid{i}": gid for i, gid in enumerate(game_ids)}

            result = await session.execute(
                text(f"""
                    SELECT
                        agent_id,
                        role,
                        AVG(won) as win_rate,
                        AVG(overall_score) as avg_score,
                        COUNT(*) as games
                    FROM player_stats
                    WHERE game_id IN ({placeholders})
                    GROUP BY role, agent_id
                    ORDER BY avg_score ASC
                """),
                params,
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def get_agent_metrics(
        self,
        agent_id: int,
        game_ids: list[str],
    ) -> dict[str, float]:
        """替代 loop._get_agent_metrics."""
        if not game_ids:
            return {"win_rate": 0, "avg_score": 0, "avg_survival": 0}

        async with async_session_maker() as session:
            placeholders = ",".join(f":gid{i}" for i in range(len(game_ids)))
            params = {f"gid{i}": gid for i, gid in enumerate(game_ids)}
            params["agent_id"] = agent_id

            result = await session.execute(
                text(f"""
                    SELECT
                        AVG(won) as win_rate,
                        AVG(overall_score) as avg_score,
                        AVG(survival_rounds) as avg_survival
                    FROM player_stats
                    WHERE agent_id = :agent_id AND game_id IN ({placeholders})
                """),
                params,
            )
            row = result.mappings().first()
            if row and row["win_rate"] is not None:
                return {
                    "win_rate": row["win_rate"] or 0,
                    "avg_score": row["avg_score"] or 0,
                    "avg_survival": row["avg_survival"] or 0,
                }
            return {"win_rate": 0, "avg_score": 0, "avg_survival": 0}
