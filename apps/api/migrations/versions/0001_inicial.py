"""Esquema inicial de F1 y siembra de planes desde config/plans.yaml.

Revision ID: 0001_inicial
Revises:
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql

from core.settings import get_settings

revision = "0001_inicial"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("limits", postgresql.JSONB, nullable=False),
    )
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("plan_id", sa.String(32), sa.ForeignKey("plans.id"), nullable=False, server_default="free"),
        sa.Column("locale", sa.String(8), nullable=False, server_default="es"),
        sa.Column("created_at", TS, server_default=sa.func.now()),
    )
    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False, server_default="stripe"),
        sa.Column("stripe_customer_id", sa.String(64)),
        sa.Column("stripe_subscription_id", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="inactive"),
        sa.Column("current_period_end", TS),
    )
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("type", sa.String(80), nullable=False),
        sa.Column("received_at", TS, server_default=sa.func.now()),
        sa.Column("processed_at", TS),
    )
    op.create_table(
        "anon_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", TS, server_default=sa.func.now()),
        sa.Column("expires_at", TS, nullable=False),
    )
    op.create_table(
        "uploads",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64)),
        sa.Column("detected_ext", sa.String(16)),
        sa.Column("detected_mime", sa.String(120)),
        sa.Column("original_name", sa.Text, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="uploading"),
        sa.Column("created_at", TS, server_default=sa.func.now()),
        sa.Column("expires_at", TS, nullable=False),
    )
    op.create_index("ix_uploads_owner", "uploads", ["owner_type", "owner_id"])
    op.create_index("ix_uploads_state_exp", "uploads", ["state", "expires_at"])
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("options", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("message", sa.Text),
        sa.Column("worker_group", sa.String(16), nullable=False),
        sa.Column("queue", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="5"),
        sa.Column("cost_class", sa.String(8), nullable=False, server_default="light"),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("has_secrets", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("heartbeat_at", TS),
        sa.Column("ai_reserved", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ai_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(40)),
        sa.Column("reserved_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", TS, server_default=sa.func.now()),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("cpu_seconds", sa.Float, nullable=False, server_default="0"),
    )
    op.create_index("uq_jobs_idempotency_live", "jobs", ["idempotency_key"], unique=True,
                    postgresql_where=sa.text("status IN ('queued','running','succeeded')"))
    op.create_index("ix_jobs_owner", "jobs", ["owner_type", "owner_id", "created_at"])
    op.create_index("ix_jobs_status_exp", "jobs", ["status", "expires_at"])
    op.create_table(
        "job_inputs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("mime", sa.String(120), nullable=False),
        sa.Column("ext", sa.String(16), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "job_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("filename", sa.String(130), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("mime", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("note", sa.Text),
    )
    op.create_table(
        "usage_daily",
        sa.Column("owner_type", sa.String(8), primary_key=True),
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("cost_class", sa.String(8), primary_key=True),
        sa.Column("tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ai_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mail_shares", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_output_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_outputs.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(130), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("downloads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("revoked_at", TS),
    )
    op.create_table(
        "tool_feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tool", sa.String(80), nullable=False, index=True),
        sa.Column("rating", sa.Integer),
        sa.Column("message", sa.Text),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now()),
    )
    op.create_table(
        "user_tool_prefs",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("favorites", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("recent", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.create_table(
        "feature_flags",
        sa.Column("slug", sa.String(80), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("plans", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target", sa.Text),
        sa.Column("created_at", TS, server_default=sa.func.now()),
    )
    data = yaml.safe_load(open(get_settings().PLANS_FILE, encoding="utf-8"))["plans"]
    op.bulk_insert(plans, [{"id": pid, "name": v["name"], "limits": {k: x for k, x in v.items() if k != "name"}} for pid, v in data.items()])


def downgrade() -> None:
    for table in ("audit_log", "feature_flags", "user_tool_prefs", "tool_feedback", "shares", "usage_daily", "job_outputs",
                  "job_inputs", "jobs", "uploads", "anon_clients", "stripe_events", "subscriptions", "profiles", "plans"):
        op.drop_table(table)
