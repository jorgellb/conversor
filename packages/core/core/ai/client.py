"""Peticiones de IA de un trabajo (6.2, 6.3 y 6.5), en `workerai`.

Cada intento, también los fallidos y los reintentos, se cuenta contra el presupuesto (del usuario y global), pasa por
el límite por minuto y se apunta en `ai_requests` sin el contenido. Con 429, 5xx o tiempo agotado se espera (con
`Retry-After` si viene) y se reintenta como mucho 2 veces, empezando por el siguiente candidato; el último intento
añade el enrutador `LLM_FALLBACK_ROUTER`.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import update

from core.ai import budget, catalog, is_excluded, quota
from core.ai.provider import LLMError, LLMProvider, LLMResult, get_provider
from core.ai.store import cache_get, cache_put
from core.ai.text import parse_json
from core.db import session_scope
from core.errors import AppError, ErrorCode, ToolError
from core.models import AiRequest, Job
from core.plans import PlanLimits
from core.settings import Settings

log = logging.getLogger("ai")
MAX_ATTEMPTS = 3  # 1 + 2 reintentos (6.3)
MAX_BACKOFF = 30.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobBudget:
    """Peticiones reservadas y usadas por un trabajo (o un mensaje del chat)."""

    settings: Settings
    r: object
    owner_type: str
    owner_id: str
    plan: PlanLimits
    reserved: int = 0
    used: int = 0
    job_id: str | None = None
    day: date | None = None

    @property
    def pro(self) -> bool:
        return self.plan.id == "pro"

    @property
    def max_task(self) -> int:
        return quota.per_task_limit(self.plan, self.settings)

    def _persist(self) -> None:
        if self.job_id:
            with session_scope() as s:
                s.execute(update(Job).where(Job.id == self.job_id).values(ai_reserved=self.reserved, ai_used=self.used))

    def _extend(self, n: int) -> None:
        if self.reserved + n > self.max_task:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, f"ai_task:{self.reserved + n}>{self.max_task}")
        try:
            with session_scope() as s:
                quota.reserve(s, self.settings, self.owner_type, self.owner_id, self.plan, n)
        except AppError as exc:
            raise ToolError(ErrorCode.QUOTA_EXCEEDED, "ai_day") from exc
        if not budget.reserve(self.r, self.settings, n, self.pro):
            with session_scope() as s:
                quota.release(s, self.settings, self.owner_type, self.owner_id, n)
            raise ToolError(ErrorCode.AI_BUDGET_EXHAUSTED, "presupuesto")
        self.reserved += n
        self._persist()

    def ensure(self, total: int) -> None:
        """Reserva lo que falte hasta `total` antes de empezar: si no cabe, el trabajo falla sin gastar nada."""
        missing = total - self.reserved
        if missing > 0:
            self._extend(missing)

    def take(self) -> None:
        """Una petición: sale de lo reservado o, si ya no queda, se reserva una más."""
        if self.used >= self.reserved:
            self._extend(1)
        self.used += 1
        self._persist()

    def settle(self) -> None:
        """Devuelve lo reservado que no se ha usado (al terminar, falle o no)."""
        unused = self.reserved - self.used
        if unused > 0:
            with session_scope() as s:
                quota.release(s, self.settings, self.owner_type, self.owner_id, unused, self.day)
            budget.release(self.r, self.settings, unused, self.day.isoformat() if self.day else None)
            self.reserved = self.used
            self._persist()


@dataclass
class AIClient:
    settings: Settings
    r: object
    tool: str
    category: str
    budget: JobBudget
    chat: bool = False
    provider: LLMProvider | None = None
    sleep: Callable[[float], None] = time.sleep
    models_used: list[str] = field(default_factory=list)

    def __post_init__(self):
        # 6.6: las herramientas excluidas no llegan nunca al proveedor, ni por error de configuración.
        if is_excluded(self.tool, self.category):
            raise ToolError(ErrorCode.AI_UNAVAILABLE, f"herramienta excluida de la IA: {self.tool}")

    # --- elección de modelos ---

    def choose(self, needs: catalog.Needs) -> tuple[list[catalog.Candidate], bool]:
        with session_scope() as s:
            cands, native = catalog.choose(s, self.settings, needs)
        if not cands:
            raise ToolError(ErrorCode.AI_UNAVAILABLE, "sin modelos que cumplan los requisitos")
        return cands, native

    def smallest(self, needs: catalog.Needs) -> catalog.Candidate:
        """El candidato de menos contexto: los bloques tienen que caber en cualquiera de los que pueden responder."""
        cands, _ = self.choose(needs)
        return min(cands, key=lambda c: (c.context_length, c.max_output))

    # --- peticiones ---

    def _provider(self) -> LLMProvider:
        if self.provider is None:
            self.provider = get_provider(self.settings)
        return self.provider

    def _wait_rpm(self) -> None:
        waited = 0.0
        while True:
            wait_ms = budget.acquire_rpm(self.r, self.settings, chat=self.chat)
            if wait_ms == 0:
                return
            if waited + wait_ms / 1000 > self.settings.AI_RPM_WAIT_SECONDS:
                raise ToolError(ErrorCode.RATE_LIMITED, "límite por minuto", transient=True)
            self.sleep(wait_ms / 1000)
            waited += wait_ms / 1000

    def _log(self, model: str | None, status: str, started: float, result: LLMResult | None = None) -> None:
        budget.count_used(self.r, self.settings)
        with session_scope() as s:
            s.add(AiRequest(owner_type=self.budget.owner_type, owner_id=self.budget.owner_id,
                            job_id=uuid.UUID(self.budget.job_id) if self.budget.job_id else None, tool=self.tool,
                            model=(model or "")[:200] or None, status=status[:24],
                            prompt_tokens=result.prompt_tokens if result else None,
                            completion_tokens=result.completion_tokens if result else None,
                            latency_ms=int((time.monotonic() - started) * 1000)))

    def _with_retries(self, needs: catalog.Needs, json_schema: dict | None,
                      invoke: Callable[[list[str], dict | None], LLMResult], retryable: Callable[[], bool]) -> LLMResult:
        cands, native = self.choose(needs)
        order = [c.id for c in cands]
        schema = json_schema if (json_schema is not None and native) else None
        last: LLMError | None = None
        for attempt in range(MAX_ATTEMPTS):
            models = order[:catalog.MAX_CANDIDATES]
            router = self.settings.LLM_FALLBACK_ROUTER
            # El enrutador gratuito puede elegir un modelo sin imágenes: con imágenes no se usa (D-243).
            if attempt == MAX_ATTEMPTS - 1 and router and router not in models and schema is None and not needs.images:
                models = (models[:catalog.MAX_CANDIDATES - 1] + [router]) if models else [router]
            self._wait_rpm()
            self.budget.take()
            started = time.monotonic()
            try:
                result = invoke(models, schema)
            except LLMError as exc:
                last = exc
                self._log(models[0], exc.kind, started)
                log.warning("petición de IA fallida", extra={"tool": self.tool, "kind": exc.kind, "status": exc.status})
                if not retryable():
                    break  # ya se ha enviado parte de la respuesta: no se repite
                if exc.kind == "data_policy":
                    with session_scope() as s:
                        catalog.pause(s, models[0])
                    order = order[1:]
                    if not order:
                        break
                    continue
                if exc.kind == "credits":
                    log.error("OpenRouter rechaza por saldo: hay que dejarlo en positivo (6.1)")
                if not exc.retryable:
                    break
                if attempt < MAX_ATTEMPTS - 1:
                    self.sleep(min(MAX_BACKOFF, exc.retry_after if exc.retry_after is not None else 2.0 ** (attempt + 1)))
                    if len(order) > 1:
                        order = order[1:] + order[:1]  # el siguiente candidato va primero
                continue
            self._log(result.model or models[0], "ok", started, result)
            if result.model:
                self.models_used.append(result.model)
            return result
        raise ToolError(ErrorCode.AI_UNAVAILABLE, last.kind if last else "sin respuesta")

    def complete(self, messages: list[dict], *, needs: catalog.Needs, max_tokens: int,
                 json_schema: dict | None = None) -> LLMResult:
        provider = self._provider()
        return self._with_retries(
            needs, json_schema,
            lambda models, schema: provider.chat(models=models, messages=messages, max_tokens=max_tokens, json_schema=schema),
            lambda: True)

    def stream(self, messages: list[dict], *, needs: catalog.Needs, max_tokens: int, on_delta: Callable[[str], None]) -> LLMResult:
        """Respuesta por trozos (chat): se reintenta como `complete` mientras no se haya enviado nada."""
        provider = self._provider()
        sent = {"any": False}

        def forward(piece: str) -> None:
            sent["any"] = True
            on_delta(piece)

        return self._with_retries(
            needs, None,
            lambda models, _schema: provider.chat_stream(models=models, messages=messages, max_tokens=max_tokens, on_delta=forward),
            lambda: not sent["any"])

    def complete_json(self, messages: list[dict], *, needs: catalog.Needs, max_tokens: int, schema: dict,
                      check: Callable[[object], object] | None = None):
        """JSON con esquema si el modelo lo admite; si no, instrucciones estrictas, lectura tolerante y como mucho una
        petición de reparación (6.5). `check` valida (y puede transformar) el resultado; si lanza, se repara."""
        json_needs = catalog.Needs(needs.context, needs.output, True, needs.images)
        _, native = self.choose(json_needs)
        msgs = list(messages)
        if not native:
            msgs = [{"role": "system", "content": "Responde SOLO con un JSON válido que cumpla este esquema, sin texto "
                     f"antes ni después y sin bloques de código: {schema}"}, *msgs]
        result = self.complete(msgs, needs=json_needs, max_tokens=max_tokens, json_schema=schema)
        try:
            data = parse_json(result.text)
            return (check(data) if check else data), result
        except (ValueError, TypeError, KeyError) as first:
            repair = [*msgs, {"role": "assistant", "content": result.text[:20000]},
                      {"role": "user", "content": f"Esa respuesta no es un JSON válido para el esquema ({first}). "
                                                  "Devuelve solo el JSON corregido."}]
            again = self.complete(repair, needs=json_needs, max_tokens=max_tokens, json_schema=schema)
            try:
                data = parse_json(again.text)
                return (check(data) if check else data), again
            except (ValueError, TypeError, KeyError) as exc:
                raise ToolError(ErrorCode.AI_UNAVAILABLE, "json inválido tras reparar") from exc


def cached(key: str, owner_type: str, owner_id: str) -> dict | None:
    with session_scope() as s:
        return cache_get(s, key, owner_type, owner_id, _now())


def remember(key: str, owner_type: str, owner_id: str, result: dict, expires_at: datetime) -> None:
    with session_scope() as s:
        cache_put(s, key, owner_type, owner_id, result, expires_at)


def settle_job(session, r, settings: Settings, job: Job) -> None:
    """Devuelve la reserva sin usar de un trabajo que muere fuera del worker (WORKER_LOST o caducado)."""
    unused = (job.ai_reserved or 0) - (job.ai_used or 0)
    if unused <= 0:
        return
    day = budget.budget_day(settings, job.created_at) if job.created_at else None
    quota.release(session, settings, job.owner_type, job.owner_id, unused, date.fromisoformat(day) if day else None)
    budget.release(r, settings, unused, day)
    job.ai_reserved = job.ai_used or 0
