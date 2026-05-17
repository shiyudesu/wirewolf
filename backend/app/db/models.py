"""SQLAlchemy ORM 模型."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Game(Base):
    """对局记录表."""

    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    winner: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    total_rounds: Mapped[int] = mapped_column(default=0)
    played_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    __table_args__ = (
        Index("idx_games_played_at", "played_at"),
    )


class PlayerStat(Base):
    """玩家单局统计表."""

    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("games.game_id"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(default=0)
    role: Mapped[str] = mapped_column(String(32), default="")
    won: Mapped[int] = mapped_column(default=0)  # 0/1
    survival_rounds: Mapped[int] = mapped_column(default=0)
    win_rate: Mapped[float] = mapped_column(default=0.0)
    seer_check_accuracy: Mapped[float] = mapped_column(default=0.0)
    witch_save_rate: Mapped[float] = mapped_column(default=0.0)
    witch_poison_accuracy: Mapped[float] = mapped_column(default=0.0)
    first_night_kill_accuracy: Mapped[float] = mapped_column(default=0.0)
    speech_quality: Mapped[float] = mapped_column(default=0.0)
    overall_score: Mapped[float] = mapped_column(default=0.0)
    strategy_version: Mapped[int] = mapped_column(default=1)
    info_utilization_score: Mapped[float] = mapped_column(default=0.0)
    defense_quality: Mapped[float] = mapped_column(default=0.0)
    vote_consistency_rate: Mapped[float] = mapped_column(default=0.0)
    model_name: Mapped[str] = mapped_column(String(128), default="")

    __table_args__ = (
        Index("idx_stats_game", "game_id"),
        Index("idx_stats_role", "role"),
        Index("idx_stats_agent", "agent_id"),
    )


class AgentProfileModel(Base):
    """Agent 策略版本表."""

    __tablename__ = "agent_profiles"

    agent_profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_version: Mapped[int] = mapped_column(primary_key=True)
    strategy_notes: Mapped[str] = mapped_column(default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
