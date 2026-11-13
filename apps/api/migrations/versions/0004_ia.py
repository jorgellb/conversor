"""IA (F3, sección 6 y 9.4): modelos descubiertos, peticiones, consentimientos, textos de documentos y caché.

`jobs.stage` guarda la etapa de un trabajo que cambia de cola (el texto de un escaneo se lee en `ocr` y la IA sigue en
`ai`). Si existe el rol de los workers (0002), recibe permisos sobre las tablas nuevas que usan los workers (9.4).

Revision ID: 0004_ia
Revises: 0003_idioma_trabajo
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004_ia"
down_revision = "0003_idioma_trabajo"
branch_labels = None
depends_on = None

ROLE = os.environ.get("WORKER_DB_USER", "conversor_worker")
WORKER_TABLES = ("ai_requests", "document_texts", "ai_cache", "llm_models")


def upgrade() -> None:
    op.add_column("jobs", sa.Column("stage", sa.String(16), nullable=True))
    op.create_table(
        "llm_models",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("context_length", sa.Integer, nullable=False),
        sa.Column("max_completion_tokens", sa.Integer, nullable=True),
        sa.Column("supports_json", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("supports_images", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("disabled_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer, nullable=True),
        sa.Column("success_rate_7d", sa.Float, nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_requests_created", "ai_requests", ["created_at"])
    op.create_index("ix_ai_requests_model", "ai_requests", ["model", "created_at"])
    op.create_table(
        "ai_consents",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("text_version", sa.String(32), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_ai_consents_day", "ai_consents", ["owner_type", "owner_id", "text_version", "day"], unique=True)
    op.create_table(
        "document_texts",
        sa.Column("owner_type", sa.String(8), primary_key=True),
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("pages", JSONB, nullable=False),
        sa.Column("extractor", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_texts_exp", "document_texts", ["expires_at"])
    op.create_table(
        "ai_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("owner_type", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_cache_exp", "ai_cache", ["expires_at"])
    conn = op.get_bind()
    if ROLE.replace("_", "").isalnum() and conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(WORKER_TABLES)} TO {ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")


def downgrade() -> None:
    for name in ("ai_cache", "document_texts", "ai_consents", "ai_requests", "llm_models"):
        op.drop_table(name)
    op.drop_column("jobs", "stage")
