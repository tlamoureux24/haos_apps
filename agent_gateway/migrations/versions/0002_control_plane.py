"""Add identities, policy revisions, events, jobs, reports and audit."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_control_plane"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("identity_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("identity_type IN ('client','event_source','scheduler')"),
        sa.CheckConstraint("status IN ('active','revoked')"),
    )
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("identity_id", sa.String(length=36), nullable=False),
        sa.Column("verifier", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=True),
        sa.Column("last_used_at", sa.String(length=32), nullable=True),
        sa.Column("revoked_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_credentials_identity", "credentials", ["identity_id"])

    op.create_table(
        "policy_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "policy_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["policy_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_id", "id"),
    )
    op.create_table(
        "policy_bindings",
        sa.Column("identity_id", sa.String(length=36), primary_key=True),
        sa.Column("policy_revision_id", sa.String(length=36), nullable=False),
        sa.Column("bound_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_revision_id"], ["policy_revisions.id"]),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_identity_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["source_identity_id"], ["identities.id"]),
        sa.UniqueConstraint("source_identity_id", "idempotency_key"),
    )
    op.create_index("ix_events_received", "events", ["received_at"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("policy_revision_id", sa.String(length=36), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["policy_revision_id"], ["policy_revisions.id"]),
        sa.CheckConstraint("state IN ('queued','leased','completed','failed','cancelled','dead_letter')"),
    )
    op.create_index("ix_jobs_state_created", "jobs", ["state", "created_at"])
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["supersedes_id"], ["reports.id"]),
    )
    op.create_index("ix_reports_job", "reports", ["job_id"])
    op.create_table(
        "audit_entries",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("occurred_at", sa.String(length=32), nullable=False),
        sa.Column("actor_identity_id", sa.String(length=36), nullable=True),
        sa.Column("credential_id", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["actor_identity_id"], ["identities.id"]),
        sa.CheckConstraint("decision IN ('allowed','denied','recorded')"),
    )


def downgrade() -> None:
    op.drop_table("audit_entries")
    op.drop_index("ix_reports_job", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_jobs_state_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_events_received", table_name="events")
    op.drop_table("events")
    op.drop_table("policy_bindings")
    op.drop_table("policy_revisions")
    op.drop_table("policy_documents")
    op.drop_index("ix_credentials_identity", table_name="credentials")
    op.drop_table("credentials")
    op.drop_table("identities")
