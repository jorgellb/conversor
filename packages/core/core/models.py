"""Modelo de datos (sección 9.4). Las tablas de Better Auth las crea `migrateauth`."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    limits: Mapped[dict] = mapped_column(JSONB)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), default="free")
    locale: Mapped[str] = mapped_column(String(8), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), default="stripe")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StripeEvent(Base):
    __tablename__ = "stripe_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnonClient(Base):
    __tablename__ = "anon_clients"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    detected_ext: Mapped[str | None] = mapped_column(String(16))
    detected_mime: Mapped[str | None] = mapped_column(String(120))
    original_name: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="uploading")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_uploads_owner", "owner_type", "owner_id"), Index("ix_uploads_state_exp", "state", "expires_at"))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(80))
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text)
    worker_group: Mapped[str] = mapped_column(String(16))
    queue: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer, default=5)
    cost_class: Mapped[str] = mapped_column(String(8), default="light")
    idempotency_key: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    has_secrets: Mapped[bool] = mapped_column(Boolean, default=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_reserved: Mapped[int] = mapped_column(Integer, default=0)
    ai_used: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cpu_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    locale: Mapped[str] = mapped_column(String(8), default="es", server_default="es")
    # Etapa en la que sigue un trabajo que pasa de una cola a otra (F3: el texto de un escaneo se lee en `ocr` y la IA
    # sigue en `ai`). Vacía en el resto.
    stage: Mapped[str | None] = mapped_column(String(16))
    inputs: Mapped[list["JobInput"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="JobInput.position")
    outputs: Mapped[list["JobOutput"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="JobOutput.position")
    __table_args__ = (
        Index(
            "uq_jobs_idempotency_live",
            "idempotency_key",
            unique=True,
            postgresql_where=text("status IN ('queued','running','succeeded')"),
        ),
        Index("ix_jobs_owner", "owner_type", "owner_id", "created_at"),
        Index("ix_jobs_status_exp", "status", "expires_at"),
    )


class JobInput(Base):
    __tablename__ = "job_inputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(120))
    ext: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64))
    job: Mapped[Job] = relationship(back_populates="inputs")


class JobOutput(Base):
    __tablename__ = "job_outputs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(130))
    path: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)
    mime: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    job: Mapped[Job] = relationship(back_populates="outputs")


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    owner_type: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    cost_class: Mapped[str] = mapped_column(String(8), primary_key=True)
    tasks: Mapped[int] = mapped_column(Integer, default=0)
    ai_requests: Mapped[int] = mapped_column(Integer, default=0)
    mail_shares: Mapped[int] = mapped_column(Integer, default=0)


class Share(Base):
    __tablename__ = "shares"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_outputs.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(130))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolFeedback(Base):
    __tablename__ = "tool_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool: Mapped[str] = mapped_column(String(80), index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserToolPrefs(Base):
    __tablename__ = "user_tool_prefs"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    favorites: Mapped[list] = mapped_column(JSONB, default=list)
    recent: Mapped[list] = mapped_column(JSONB, default=list)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    plans: Mapped[list] = mapped_column(JSONB, default=list)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- IA (6 y 9.4) ---


class LlmModel(Base):
    """Modelos gratuitos de OpenRouter descubiertos (6.2)."""

    __tablename__ = "llm_models"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    context_length: Mapped[int] = mapped_column(Integer)
    max_completion_tokens: Mapped[int | None] = mapped_column(Integer)
    supports_json: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_images: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    disabled_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Preferencia fijada en el panel de administración: menor, antes. Vacía, sin preferencia.
    priority: Mapped[int | None] = mapped_column(Integer)
    success_rate_7d: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiRequest(Base):
    """Cada petición real a OpenRouter, también los fallos y los reintentos (6.3). Nunca el contenido."""

    __tablename__ = "ai_requests"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tool: Mapped[str] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_ai_requests_created", "created_at"), Index("ix_ai_requests_model", "model", "created_at"))


class AiConsent(Base):
    """Consentimiento del aviso de IA (6.6): uno por usuario, versión del texto y día."""

    __tablename__ = "ai_consents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    text_version: Mapped[str] = mapped_column(String(32))
    day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("uq_ai_consents_day", "owner_type", "owner_id", "text_version", "day", unique=True),)


class DocumentText(Base):
    """Texto de un documento por páginas, de un solo propietario; caduca con sus archivos (6.4 y 9.4)."""

    __tablename__ = "document_texts"
    owner_type: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    pages: Mapped[list] = mapped_column(JSONB, default=list)
    extractor: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiCache(Base):
    """Resultados de IA por (propietario, documento, herramienta, opciones, idioma); nunca se comparten (6.5)."""

    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(8))
    owner_id: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# --- Firma (F4, 9.4 y 10) -------------------------------------------------------------------------------------------


class SignatureRequest(Base):
    """solicitar-firmas (F4-C): el documento se guarda aparte, en /srv/files/requests/<id> (desviación de 4.1)."""

    __tablename__ = "signature_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    job_output_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_outputs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Signer(Base):
    __tablename__ = "signers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    sign_order: Mapped[int] = mapped_column(Integer, default=0)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # solo el hash del token (12.6)
    code_hash: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Eventos de una solicitud de firmas; alimentan su certificado de auditoría."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(320))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SealSignature(Base):
    """Cada uso del sello de la plataforma (10): sin clave ajena al trabajo, para que sobreviva al borrado de este."""

    __tablename__ = "seal_signatures"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_sha256: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
