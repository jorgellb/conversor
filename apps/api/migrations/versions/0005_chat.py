"""chat-pdf (F3, 6.4, 6.5 y 9.4): fragmentos de los documentos con su vector en pgvector.

La extensión `vector` viene en la imagen de PostgreSQL (pgvector). Los fragmentos son de un solo propietario y caducan
con sus archivos. Sin índice aproximado: cada búsqueda se limita a un documento (propietario y SHA-256) y recorre sus
fragmentos con la distancia del coseno, que es exacta y rápida para unos miles de filas.

Revision ID: 0005_chat
Revises: 0004_ia
"""
from __future__ import annotations

import os

from alembic import op
from sqlalchemy import text

revision = "0005_chat"
down_revision = "0004_ia"
branch_labels = None
depends_on = None

ROLE = os.environ.get("WORKER_DB_USER", "conversor_worker")
DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"""
        CREATE TABLE document_chunks (
            id BIGSERIAL PRIMARY KEY,
            owner_type VARCHAR(8) NOT NULL,
            owner_id VARCHAR(64) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            page INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            embedding vector({DIM}) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_document_chunks_doc ON document_chunks (owner_type, owner_id, sha256, chunk_index)")
    op.execute("CREATE INDEX ix_document_chunks_exp ON document_chunks (expires_at)")
    conn = op.get_bind()
    if ROLE.replace("_", "").isalnum() and conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}).scalar():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO {ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_chunks")
