"""Idioma de la página que crea el trabajo (F2, lote C).

Los textos que van dentro del resultado (cabeceras de un correo, título del índice de un libro, marcadores de una
solicitud de empleo) salen en ese idioma. Los permisos del rol de los workers son de tabla: no hace falta tocarlos.

Revision ID: 0003_idioma_trabajo
Revises: 0002_rol_workers
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_idioma_trabajo"
down_revision = "0002_rol_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("locale", sa.String(8), nullable=False, server_default="es"))


def downgrade() -> None:
    op.drop_column("jobs", "locale")
