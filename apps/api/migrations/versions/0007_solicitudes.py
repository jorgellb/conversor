"""solicitar-firmas (7.7, F4-C2, D-202): lo que necesita el flujo sobre las tablas de 0006.

La API y beat (usuario principal) son los únicos que escriben en `signature_requests`, `signers` y `audit_events`; los
workers siguen sin permisos sobre ellas: sus trabajos (propietario «request») reciben por opciones lo que necesitan.

Revision ID: 0007_solicitudes
Revises: 0006_firma
"""
from __future__ import annotations

from alembic import op

revision = "0007_solicitudes"
down_revision = "0006_firma"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE signature_requests
            ADD COLUMN document_name VARCHAR(200) NOT NULL DEFAULT '',
            ADD COLUMN filename VARCHAR(130) NOT NULL DEFAULT '',
            ADD COLUMN message TEXT,
            ADD COLUMN sequential BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN locale VARCHAR(2) NOT NULL DEFAULT 'es',
            ADD COLUMN owner_email VARCHAR(320) NOT NULL DEFAULT '',
            ADD COLUMN original_sha256 VARCHAR(64),
            ADD COLUMN document_sha256 VARCHAR(64),
            ADD COLUMN final_job_id UUID,
            ADD COLUMN final_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN final_files JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN completed_at TIMESTAMPTZ,
            ADD COLUMN purged_at TIMESTAMPTZ
    """)
    op.execute("CREATE INDEX ix_signature_requests_status ON signature_requests (status)")
    op.execute("""
        ALTER TABLE signers
            ADD COLUMN field VARCHAR(120) NOT NULL DEFAULT '',
            ADD COLUMN job_id UUID,
            ADD COLUMN job_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN code_expires_at TIMESTAMPTZ,
            ADD COLUMN code_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN invited_at TIMESTAMPTZ,
            ADD COLUMN viewed_at TIMESTAMPTZ
    """)
    op.execute("ALTER TABLE audit_events ADD COLUMN detail TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS detail")
    for column in ("field", "job_id", "job_attempts", "code_expires_at", "code_attempts", "invited_at", "viewed_at"):
        op.execute(f"ALTER TABLE signers DROP COLUMN IF EXISTS {column}")
    op.execute("DROP INDEX IF EXISTS ix_signature_requests_status")
    for column in ("document_name", "filename", "message", "sequential", "locale", "owner_email", "original_sha256",
                   "document_sha256", "final_job_id", "final_attempts", "final_files", "completed_at", "purged_at"):
        op.execute(f"ALTER TABLE signature_requests DROP COLUMN IF EXISTS {column}")
