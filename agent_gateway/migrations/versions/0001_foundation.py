"""Create the foundation metadata tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_metadata",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.bulk_insert(
        sa.table("gateway_metadata", sa.column("key"), sa.column("value")),
        [
            {"key": "application", "value": "agent_gateway"},
            {"key": "data_schema", "value": "1"},
        ],
    )


def downgrade() -> None:
    op.drop_table("gateway_metadata")
