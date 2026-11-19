"""Firma (F4, 9.4 y 10): solicitudes de firma, firmantes, eventos de auditoría y registro de usos del sello.

El rol de los workers solo puede leer y añadir en `seal_signatures` (9.4): `workersign` cuenta los sellos del día
(SEAL_DAILY_LIMIT) y anota cada uso. Las solicitudes, firmantes y eventos son de la API (F4-C).

Revision ID: 0006_firma
Revises: 0005_chat
"""
from __future__ import annotations

import os

from alembic import op
from sqlalchemy import text

revision = "0006_firma"
down_revision = "0005_chat"
branch_labels = None
depends_on = None

ROLE = os.environ.get("WORKER_DB_USER", "conversor_worker")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE signature_requests (
            id UUID PRIMARY KEY,
            owner_id VARCHAR(64) NOT NULL,
            job_output_id UUID REFERENCES job_outputs(id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_signature_requests_owner_id ON signature_requests (owner_id)")
    op.execute("CREATE INDEX ix_signature_requests_expires_at ON signature_requests (expires_at)")
    op.execute("""
        CREATE TABLE signers (
            id UUID PRIMARY KEY,
            request_id UUID NOT NULL REFERENCES signature_requests(id) ON DELETE CASCADE,
            email VARCHAR(320) NOT NULL,
            name VARCHAR(200) NOT NULL,
            sign_order INTEGER NOT NULL DEFAULT 0,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            code_hash VARCHAR(128),
            status VARCHAR(16) NOT NULL,
            signed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX ix_signers_request_id ON signers (request_id)")
    op.execute("""
        CREATE TABLE audit_events (
            id BIGSERIAL PRIMARY KEY,
            request_id UUID NOT NULL REFERENCES signature_requests(id) ON DELETE CASCADE,
            event VARCHAR(40) NOT NULL,
            actor VARCHAR(320) NOT NULL,
            ip_hash VARCHAR(64),
            user_agent TEXT,
            document_sha256 VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_audit_events_request_id ON audit_events (request_id)")
    op.execute("""
        CREATE TABLE seal_signatures (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL,
            document_sha256 VARCHAR(64) NOT NULL,
            level VARCHAR(8) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_seal_signatures_created_at ON seal_signatures (created_at)")
    conn = op.get_bind()
    if ROLE.replace("_", "").isalnum() and conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar():
        op.execute(f"GRANT SELECT, INSERT ON seal_signatures TO {ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE seal_signatures_id_seq TO {ROLE}")


def downgrade() -> None:
    for table in ("seal_signatures", "audit_events", "signers", "signature_requests"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
