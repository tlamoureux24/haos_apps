"""Add persistent per-identity event intake rate windows."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_intake_rate_limits"
down_revision = "0002_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intake_rate_windows",
        sa.Column("identity_id", sa.String(length=36), primary_key=True),
        sa.Column("window_started_at", sa.String(length=32), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
        sa.CheckConstraint("request_count >= 0"),
    )


def downgrade() -> None:
    op.drop_table("intake_rate_windows")
