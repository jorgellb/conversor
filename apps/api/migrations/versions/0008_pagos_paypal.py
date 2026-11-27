"""Pagos con PayPal, pase de 24 h, pedidos y facturas (D-273).

Sustituye la suscripción de Stripe (decisión 6, D-16): las herramientas ligeras son gratis y las pesadas y de IA piden un
pase de 24 h por 1 € (IVA incluido), que se paga solo con PayPal (cuenta o tarjeta). Las facturas no se modifican ni se
borran nunca (un disparador lo impide): una devolución emite una rectificativa.

Revision ID: 0008_pagos_paypal
Revises: 0007_solicitudes
"""
from __future__ import annotations

import json

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql

from core.settings import get_settings

revision = "0008_pagos_paypal"
down_revision = "0007_solicitudes"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def _sync_plans() -> None:
    """Los nombres y límites de config/plans.yaml (el de Pro pasa a ser el del pase)."""
    data = yaml.safe_load(open(get_settings().PLANS_FILE, encoding="utf-8"))["plans"]
    conn = op.get_bind()
    for pid, values in data.items():
        limits = {k: v for k, v in values.items() if k != "name"}
        conn.execute(sa.text("UPDATE plans SET name = :n, limits = CAST(:l AS JSONB) WHERE id = :i"),
                     {"n": values["name"], "l": json.dumps(limits), "i": pid})


def upgrade() -> None:
    op.add_column("profiles", sa.Column("pass_until", TS))
    op.drop_table("subscriptions")
    op.drop_table("stripe_events")
    op.create_table(
        "billing_profiles",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("tax_id", sa.String(32), nullable=False, server_default=""),
        sa.Column("address", sa.String(300), nullable=False, server_default=""),
        sa.Column("postal_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("city", sa.String(120), nullable=False, server_default=""),
        sa.Column("country", sa.String(2), nullable=False, server_default="ES"),
        sa.Column("updated_at", TS, server_default=sa.func.now()),
    )
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("product", sa.String(32), nullable=False, server_default="pass24h"),
        sa.Column("hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("base_cents", sa.Integer, nullable=False),
        sa.Column("vat_cents", sa.Integer, nullable=False),
        sa.Column("vat_rate_bp", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="created", index=True),
        sa.Column("provider", sa.String(16), nullable=False, server_default="paypal"),
        sa.Column("provider_order_id", sa.String(64), unique=True),
        sa.Column("provider_capture_id", sa.String(64), unique=True),
        sa.Column("payer_email", sa.String(320)),
        sa.Column("locale", sa.String(2), nullable=False, server_default="es"),
        sa.Column("waiver_at", TS),
        sa.Column("created_at", TS, server_default=sa.func.now()),
        sa.Column("paid_at", TS),
        sa.Column("refunded_at", TS),
        sa.CheckConstraint("status IN ('created', 'paid', 'refunded', 'failed')", name="ck_orders_status"),
        sa.CheckConstraint("total_cents > 0 AND base_cents + vat_cents = total_cents", name="ck_orders_amounts"),
    )
    op.create_table(
        "passes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("starts_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.CheckConstraint("expires_at > starts_at", name="ck_passes_range"),
    )
    op.create_table(
        "invoice_counters",
        sa.Column("series", sa.String(16), primary_key=True),
        sa.Column("last", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False, unique=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("series", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(4), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False, index=True),
        sa.Column("rectifies_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id")),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("issued_at", TS, nullable=False),
        sa.Column("issuer", postgresql.JSONB, nullable=False),
        sa.Column("buyer", postgresql.JSONB, nullable=False),
        sa.Column("lines", postgresql.JSONB, nullable=False),
        sa.Column("base_cents", sa.Integer, nullable=False),
        sa.Column("vat_rate_bp", sa.Integer, nullable=False),
        sa.Column("vat_cents", sa.Integer, nullable=False),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("record_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("record_at", sa.String(32), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False, server_default="es"),
        sa.CheckConstraint("kind IN ('F1', 'F2', 'R1', 'R5')", name="ck_invoices_kind"),
        sa.CheckConstraint("base_cents + vat_cents = total_cents", name="ck_invoices_amounts"),
    )
    # Solo una factura de alta por pedido y una rectificativa por factura.
    op.execute("CREATE UNIQUE INDEX ux_invoices_order_alta ON invoices (order_id) WHERE rectifies_id IS NULL")
    op.execute("CREATE UNIQUE INDEX ux_invoices_rectifies ON invoices (rectifies_id) WHERE rectifies_id IS NOT NULL")
    op.execute("""
        CREATE FUNCTION invoices_inmutables() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Las facturas emitidas no se modifican ni se borran: emite una rectificativa';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER tr_invoices_inmutables BEFORE UPDATE OR DELETE ON invoices
        FOR EACH ROW EXECUTE FUNCTION invoices_inmutables()
    """)
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False, server_default="paypal"),
        sa.Column("type", sa.String(80), nullable=False),
        sa.Column("received_at", TS, server_default=sa.func.now()),
        sa.Column("processed_at", TS),
    )
    _sync_plans()


def downgrade() -> None:
    op.drop_table("payment_events")
    op.execute("DROP TRIGGER tr_invoices_inmutables ON invoices")
    op.execute("DROP FUNCTION invoices_inmutables()")
    for table in ("invoices", "invoice_counters", "passes", "orders", "billing_profiles"):
        op.drop_table(table)
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
    op.drop_column("profiles", "pass_until")
