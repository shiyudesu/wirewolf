"""Leaderboard — 排行榜数据存储（PostgreSQL 异步版）."""

from __future__ import annotations

from typing import Optional

from app.db.database import AsyncLeaderboardDB
from app.evaluation.metrics import AgentOutcomeMetrics, AgentProcessMetrics


class LeaderboardDB(AsyncLeaderboardDB):
    """排行榜数据库（兼容旧类名）.

    使用方式：所有方法需 await 调用。
    例：
        db = LeaderboardDB()
        await db.init_db()            # 首次运行建议显式建表
        await db.record_game(...)
    """

    def __init__(self) -> None:
        super().__init__()
