"""Descubrimiento y elección de modelos gratuitos (6.2).

Se guardan los modelos con precio 0 en entrada y salida (lleven o no `:free`) con su contexto, su salida máxima, si
admiten salida JSON y si admiten imagen. Para cada petición se eligen hasta 3 candidatos que cumplan lo que pide la
tarea, en este orden: `LLM_PREFERRED_MODELS`, la preferencia del panel de administración, la tasa de éxito propia de
los últimos 7 días y el contexto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.models import LlmModel
from core.settings import Settings

MAX_CANDIDATES = 3
DATA_POLICY_PAUSE = timedelta(hours=24)


@dataclass(frozen=True)
class Needs:
    """Lo que una petición exige al modelo."""

    context: int = 8000  # tokens de entrada y salida juntos
    output: int = 1000  # tokens de salida
    json: bool = False
    images: bool = False


@dataclass(frozen=True)
class Candidate:
    id: str
    context_length: int
    max_completion_tokens: int | None
    supports_json: bool
    supports_images: bool

    @property
    def max_output(self) -> int:
        """Salida máxima: la declarada o, si el modelo no la declara, una cuarta parte del contexto."""
        return self.max_completion_tokens or max(1000, self.context_length // 4)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _zero(value) -> bool:
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError):
        return False


def parse_models(data: list[dict]) -> list[dict]:
    """Del listado de `/models`, los gratuitos con lo que hace falta para elegirlos."""
    found = []
    for m in data:
        pricing = m.get("pricing") or {}
        if not (_zero(pricing.get("prompt", "1")) and _zero(pricing.get("completion", "1"))):
            continue
        # Un precio por petición o por imagen distinto de 0 tampoco es gratis.
        if any(not _zero(pricing.get(k, "0")) for k in ("request", "image")):
            continue
        context = m.get("context_length") or (m.get("top_provider") or {}).get("context_length")
        if not context or not m.get("id"):
            continue
        params = set(m.get("supported_parameters") or [])
        modalities = set(((m.get("architecture") or {}).get("input_modalities")) or [])
        found.append({
            "id": str(m["id"])[:200],
            "context_length": int(context),
            "max_completion_tokens": (m.get("top_provider") or {}).get("max_completion_tokens"),
            "supports_json": bool(params & {"response_format", "structured_outputs"}),
            "supports_images": "image" in modalities,
        })
    return found


def upsert_models(session: Session, models: list[dict], now: datetime | None = None) -> int:
    now = now or utcnow()
    for m in models:
        row = session.get(LlmModel, m["id"])
        if row is None:
            row = LlmModel(id=m["id"], enabled=True)
            session.add(row)
        row.context_length = m["context_length"]
        row.max_completion_tokens = int(m["max_completion_tokens"]) if m.get("max_completion_tokens") else None
        row.supports_json = m["supports_json"]
        row.supports_images = m["supports_images"]
        row.last_seen_at = now
    return len(models)


def update_success_rates(session: Session) -> None:
    """Tasa de éxito de los últimos 7 días por modelo (con al menos 5 peticiones; si no, sin dato)."""
    session.execute(text(
        """
        UPDATE llm_models m SET success_rate_7d = s.rate
        FROM (
            SELECT model, CASE WHEN count(*) >= 5 THEN avg(CASE WHEN status = 'ok' THEN 1.0 ELSE 0.0 END) END AS rate
            FROM ai_requests WHERE created_at > now() - interval '7 days' AND model IS NOT NULL GROUP BY model
        ) s WHERE m.id = s.model
        """
    ))


def _fresh_since(settings: Settings, now: datetime) -> datetime:
    # Un modelo que no aparece en dos descubrimientos seguidos ya no se ofrece (los gratuitos rotan sin aviso).
    return now - timedelta(hours=max(1, settings.LLM_MODELS_REFRESH_HOURS) * 2 + 1)


def usable(session: Session, settings: Settings, now: datetime | None = None) -> list[Candidate]:
    now = now or utcnow()
    rows = session.scalars(
        select(LlmModel).where(
            LlmModel.enabled.is_(True),
            (LlmModel.disabled_until.is_(None)) | (LlmModel.disabled_until < now),
            LlmModel.last_seen_at >= _fresh_since(settings, now),
        )
    ).all()
    preferred = settings.preferred_models

    def order(m: LlmModel) -> tuple:
        pref = preferred.index(m.id) if m.id in preferred else len(preferred)
        prio = m.priority if m.priority is not None else 10_000
        rate = m.success_rate_7d if m.success_rate_7d is not None else 0.5
        return (pref, prio, -rate, -m.context_length, m.id)

    return [Candidate(m.id, m.context_length, m.max_completion_tokens, m.supports_json, m.supports_images)
            for m in sorted(rows, key=order)]


def fits(c: Candidate, needs: Needs) -> bool:
    if needs.images and not c.supports_images:
        return False
    return c.context_length >= needs.context and c.max_output >= needs.output


def choose(session: Session, settings: Settings, needs: Needs, exclude: set[str] | None = None) -> tuple[list[Candidate], bool]:
    """Hasta 3 candidatos y si van con salida JSON nativa.

    Con `needs.json`, se prefieren los que admiten `response_format`; si no hay ninguno, se usan los demás con
    instrucciones estrictas y reparación (6.5). Sin candidatos, la lista va vacía: AI_UNAVAILABLE sin gastar.
    """
    pool = [c for c in usable(session, settings) if fits(c, needs) and c.id not in (exclude or set())]
    if needs.json:
        native = [c for c in pool if c.supports_json]
        if native:
            return native[:MAX_CANDIDATES], True
    return pool[:MAX_CANDIDATES], False


def available(session: Session, settings: Settings, needs: Needs) -> bool:
    return bool(choose(session, settings, needs)[0])


def pause(session: Session, model_id: str, now: datetime | None = None) -> None:
    """6.2: un modelo sin ningún proveedor que cumpla `data_collection: "deny"` se aparta 24 horas."""
    row = session.get(LlmModel, model_id)
    if row is not None:
        row.disabled_until = (now or utcnow()) + DATA_POLICY_PAUSE
