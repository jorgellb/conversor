"""Rol de PostgreSQL limitado para los workers (9.4).

Solo se crea si el servicio `migrate` recibe WORKER_DB_PASSWORD (en Coolify, SERVICE_PASSWORD_WORKERDB).
Además de las tablas de 9.4, el rol puede leer `plans` y `profiles` para aplicar los límites del plan
(anotado en docs/DECISIONS.md).

Revision ID: 0002_rol_workers
Revises: 0001_inicial
"""
from __future__ import annotations

import os

from alembic import op
from sqlalchemy import text

revision = "0002_rol_workers"
down_revision = "0001_inicial"
branch_labels = None
depends_on = None

ROLE = os.environ.get("WORKER_DB_USER", "conversor_worker")
WRITE = ("jobs", "job_inputs", "job_outputs", "usage_daily")
READ = ("plans", "profiles")


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    password = os.environ.get("WORKER_DB_PASSWORD", "")
    if not password:
        return
    if not ROLE.replace("_", "").isalnum():
        raise ValueError("WORKER_DB_USER no válido")
    conn = op.get_bind()
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar()
    verb = "ALTER" if exists else "CREATE"
    op.execute(f"{verb} ROLE {ROLE} WITH LOGIN PASSWORD {_literal(password)} NOSUPERUSER NOCREATEDB NOCREATEROLE")
    op.execute(f"GRANT CONNECT ON DATABASE {conn.engine.url.database} TO {ROLE}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(WRITE)} TO {ROLE}")
    op.execute(f"GRANT SELECT ON {', '.join(READ)} TO {ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar():
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
        op.execute(f"DROP ROLE {ROLE}")
