"""init tables

Revision ID: 001
Revises:
Create Date: 2026-05-17 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("game_id", sa.String(64), primary_key=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("winner", sa.String(32), nullable=True),
        sa.Column("total_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("played_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_games_played_at", "games", ["played_at"])

    op.create_table(
        "player_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(32), nullable=False, server_default=""),
        sa.Column("won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("survival_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("seer_check_accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("witch_save_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("witch_poison_accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("first_night_kill_accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("speech_quality", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("strategy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("info_utilization_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("defense_quality", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("vote_consistency_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("model_name", sa.String(128), nullable=False, server_default=""),
    )
    op.create_index("idx_stats_game", "player_stats", ["game_id"])
    op.create_index("idx_stats_role", "player_stats", ["role"])
    op.create_index("idx_stats_agent", "player_stats", ["agent_id"])

    op.create_table(
        "agent_profiles",
        sa.Column("agent_profile_id", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(32), primary_key=True),
        sa.Column("strategy_version", sa.Integer(), primary_key=True),
        sa.Column("strategy_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_profiles")
    op.drop_table("player_stats")
    op.drop_table("games")
