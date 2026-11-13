"""Proveedores de LLM (6.6): `LLMProvider` para OpenRouter hoy y, si llega, uno de pago con retención cero mañana.

`OpenRouterProvider` habla la API compatible con OpenAI de OpenRouter a través de `egressai` (Smokescreen). Todas las
peticiones llevan `provider.data_collection: "deny"`, que no se puede cambiar. `FakeProvider` es determinista y se usa
en desarrollo y en las pruebas cuando no hay clave.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)
DATA_POLICY = re.compile(r"data[ _-]?(policy|collection)", re.I)


@dataclass
class LLMResult:
    text: str
    model: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMError(Exception):
    """Fallo de una petición. `kind`: rate_limited, server_error, timeout, data_policy, credits, auth, bad_request."""

    RETRYABLE = frozenset({"rate_limited", "server_error", "timeout"})

    def __init__(self, kind: str, status: int | None = None, retry_after: float | None = None, detail: str = ""):
        super().__init__(f"{kind} ({status}): {detail[:200]}")
        self.kind = kind
        self.status = status
        self.retry_after = retry_after
        self.detail = detail[:500]

    @property
    def retryable(self) -> bool:
        return self.kind in self.RETRYABLE


class LLMProvider(Protocol):
    def chat(self, *, models: list[str], messages: list[dict], max_tokens: int, json_schema: dict | None = None,
             temperature: float = 0.2) -> LLMResult: ...

    def chat_stream(self, *, models: list[str], messages: list[dict], max_tokens: int, on_delta,
                    temperature: float = 0.2) -> LLMResult: ...

    def list_models(self) -> list[dict]: ...

    def key_info(self) -> dict: ...


def request_body(models: list[str], messages: list[dict], max_tokens: int, json_schema: dict | None, temperature: float) -> dict:
    body: dict = {
        "model": models[0],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # 6.1 y 6.6: solo proveedores que no recogen los datos. Fijo en el código: no hay forma de cambiarlo.
        "provider": {"data_collection": "deny"},
    }
    if len(models) > 1:
        body["models"] = models
    if json_schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "respuesta", "strict": True, "schema": json_schema}}
        # Solo endpoints que admiten la salida estructurada (si no, OpenRouter lo ignoraría en silencio).
        body["provider"]["require_parameters"] = True
    return body


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def error_from(response: httpx.Response) -> LLMError:
    try:
        payload = response.json()
        detail = json.dumps(payload.get("error", payload), ensure_ascii=False)
    except ValueError:
        detail = response.text
    status = response.status_code
    if status == 429:
        return LLMError("rate_limited", status, _retry_after(response), detail)
    if status in (408, 504):
        return LLMError("timeout", status, _retry_after(response), detail)
    if status >= 500:
        return LLMError("server_error", status, _retry_after(response), detail)
    if status == 402:
        return LLMError("credits", status, None, detail)
    if status in (401, 403):
        return LLMError("auth", status, None, detail)
    if status == 404 and DATA_POLICY.search(detail):
        return LLMError("data_policy", status, None, detail)
    if status == 404:
        return LLMError("server_error", status, None, detail)  # ningún proveedor disponible ahora mismo
    return LLMError("bad_request", status, None, detail)


class OpenRouterProvider:
    def __init__(self, base_url: str, api_key: str, *, proxy: str | None = None, referer: str = "", title: str = "",
                 transport: httpx.BaseTransport | None = None):
        headers = {"Authorization": f"Bearer {api_key}"}
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        kwargs: dict = {"base_url": base_url.rstrip("/") + "/", "headers": headers, "timeout": TIMEOUT}
        if transport is not None:
            kwargs["transport"] = transport
        elif proxy:
            kwargs["proxy"] = proxy
        self._http = httpx.Client(**kwargs)

    def chat(self, *, models: list[str], messages: list[dict], max_tokens: int, json_schema: dict | None = None,
             temperature: float = 0.2) -> LLMResult:
        try:
            response = self._http.post("chat/completions", json=request_body(models, messages, max_tokens, json_schema, temperature))
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", None, None, type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise LLMError("server_error", None, None, type(exc).__name__) from exc
        if response.status_code != 200:
            raise error_from(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("server_error", 200, None, "respuesta que no es JSON") from exc
        if data.get("error"):
            # Errores que llegan con 200 (p. ej., un proveedor que falla a mitad).
            err = data["error"]
            code = int(err.get("code") or 502) if str(err.get("code", "")).isdigit() else 502
            fake = httpx.Response(code, json={"error": err})
            raise error_from(fake)
        choices = data.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(content, str) or not content.strip():
            raise LLMError("server_error", 200, None, "respuesta vacía")
        usage = data.get("usage") or {}
        return LLMResult(content, data.get("model"), usage.get("prompt_tokens"), usage.get("completion_tokens"))

    def chat_stream(self, *, models: list[str], messages: list[dict], max_tokens: int, on_delta,
                    temperature: float = 0.2) -> LLMResult:
        """Respuesta por eventos (`stream: true`): llama a `on_delta` con cada trozo de texto."""
        body = request_body(models, messages, max_tokens, None, temperature)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        parts: list[str] = []
        model = None
        usage: dict = {}
        try:
            with self._http.stream("POST", "chat/completions", json=body) as response:
                if response.status_code != 200:
                    response.read()
                    raise error_from(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue  # comentarios de espera («: OPENROUTER PROCESSING»)
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        raise LLMError("server_error", 200, None, json.dumps(chunk["error"], ensure_ascii=False))
                    model = chunk.get("model") or model
                    usage = chunk.get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            parts.append(piece)
                            on_delta(piece)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", None, None, type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise LLMError("server_error", None, None, type(exc).__name__) from exc
        text = "".join(parts)
        if not text.strip():
            raise LLMError("server_error", 200, None, "respuesta vacía")
        return LLMResult(text, model, usage.get("prompt_tokens"), usage.get("completion_tokens"))

    def list_models(self) -> list[dict]:
        response = self._http.get("models")
        if response.status_code != 200:
            raise error_from(response)
        return response.json().get("data") or []

    def key_info(self) -> dict:
        response = self._http.get("key")
        if response.status_code != 200:
            raise error_from(response)
        return response.json().get("data") or {}


FAKE_MODEL = {
    "id": "falso/modelo-de-prueba:free",
    "context_length": 32768,
    "pricing": {"prompt": "0", "completion": "0"},
    "top_provider": {"context_length": 32768, "max_completion_tokens": 4096},
    "supported_parameters": ["max_tokens", "temperature", "response_format", "structured_outputs"],
    "architecture": {"input_modalities": ["text", "image"]},
}


def _fake_value(schema: dict, seed: str, depth: int = 0, ctx: dict | None = None, name: str = ""):
    """JSON que cumple el esquema y que tiene sentido para las herramientas: tantos elementos como pide la instrucción
    («exactamente N»), la página del texto, la opción 0 como correcta y las traducciones alineadas con la entrada."""
    ctx = ctx or {}
    kind = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if kind == "object":
        props = schema.get("properties") or {}
        return {k: _fake_value(v, f"{seed}.{k}", depth + 1, ctx, k) for k, v in props.items()}
    if kind == "array":
        if name == "traducciones" and ctx.get("items") is not None:
            return [f"[{ctx.get('target', 'xx')}] {item}" for item in ctx["items"]]
        if name in ("preguntas", "fichas", "diapositivas", "secciones") and ctx.get("count"):
            n = ctx["count"] if name != "secciones" else 3
        elif name == "opciones":
            n = ctx.get("options", 4) if not ctx.get("no_options") else 0
        elif "minItems" in schema:
            n = int(schema["minItems"])
        else:
            n = 3 if depth < 3 else 1
        return [_fake_value(schema.get("items") or {"type": "string"}, f"{seed}[{i}]", depth + 1, ctx, name) for i in range(n)]
    if kind in ("integer", "number"):
        if name == "correcta":
            return 0
        if name in ("pagina", "paginas"):
            return ctx.get("page", 1)
        return int(hashlib.sha256(seed.encode()).hexdigest()[:4], 16) % 100
    if kind == "boolean":
        return True
    words = ctx.get("words") or []
    tag = hashlib.sha256(seed.encode()).hexdigest()[:6]
    if name in ("enunciado", "anverso", "titulo") and words:
        k = int(tag, 16) % max(1, len(words))
        return f"{' '.join(words[k:k + 6]) or 'Texto'} ({tag})"
    return f"Texto de prueba {tag}"


def _fake_context(messages: list[dict], content: str) -> dict:
    system = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    ctx: dict = {}
    if m := re.search(r"exactamente (\d+)", system):
        ctx["count"] = int(m.group(1))
    if m := re.search(r"(\d+) opciones", system):
        ctx["options"] = int(m.group(1))
    if "verdadero o falso" in system and "test" not in system:
        ctx["no_options"] = True
    if m := re.search(r"al (\w+) cada elemento", system):
        ctx["target"] = m.group(1)
    inside = content.split("<<<", 1)[-1].split(">>>", 1)[0] if "<<<" in content else content
    if m := re.search(r"\[Página (\d+)\]", inside):
        ctx["page"] = int(m.group(1))
    if "traduc" in system.lower():
        try:
            items = json.loads(inside.strip())
            if isinstance(items, list):
                ctx["items"] = [str(i) for i in items]
        except ValueError:
            pass
    ctx["words"] = re.findall(r"[^\W\d_][\w'’-]*", inside)[:400]
    return ctx


class FakeProvider:
    """Determinista: el texto se deriva de lo que recibe. Para desarrollo sin clave y para las pruebas (6.6)."""

    def __init__(self):
        self.calls: list[dict] = []

    def chat(self, *, models: list[str], messages: list[dict], max_tokens: int, json_schema: dict | None = None,
             temperature: float = 0.2) -> LLMResult:
        body = request_body(models, messages, max_tokens, json_schema, temperature)
        self.calls.append(body)
        last = next((m for m in reversed(messages) if m.get("role") == "user"), {"content": ""})
        content = last["content"] if isinstance(last["content"], str) else json.dumps(last["content"], ensure_ascii=False)
        prompt_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4
        if json_schema is not None:
            text = json.dumps(_fake_value(json_schema, content[:200], ctx=_fake_context(messages, content)), ensure_ascii=False)
        else:
            inside = content.split("<<<", 1)[-1].split(">>>", 1)[0] if "<<<" in content else content
            words = re.findall(r"\w[\w'’-]*", inside)
            if "Pregunta:" in content:
                page = re.search(r"\[Página (\d+)\]", content)
                text = (f"Respuesta de prueba (modelo falso) a «{content.rsplit('Pregunta:', 1)[-1].strip()[:80]}»: "
                        + " ".join(words[:20]) + (f" (pág. {page.group(1)})" if page else ""))
            else:
                text = "- Resumen de prueba (modelo falso): " + " ".join(words[:40]) + "\n- " + " ".join(words[40:80])
        time.sleep(0)
        return LLMResult(text, models[0], prompt_tokens, len(text) // 4)

    def chat_stream(self, *, models: list[str], messages: list[dict], max_tokens: int, on_delta,
                    temperature: float = 0.2) -> LLMResult:
        result = self.chat(models=models, messages=messages, max_tokens=max_tokens, temperature=temperature)
        self.calls[-1]["stream"] = True
        words = result.text.split(" ")
        for i in range(0, len(words), 4):
            on_delta(" ".join(words[i:i + 4]) + (" " if i + 4 < len(words) else ""))
        return result

    def list_models(self) -> list[dict]:
        return [FAKE_MODEL]

    def key_info(self) -> dict:
        used = len(self.calls)
        return {"label": "falsa", "usage": 0, "limit": None, "is_free_tier": False,
                "free_model_daily_requests": {"used": used, "limit": 1000, "remaining": 1000 - used}}


_OVERRIDE: dict[str, LLMProvider | None] = {"provider": None}
_FAKE = FakeProvider()


def set_provider(provider: LLMProvider | None) -> None:
    """Para las pruebas: sustituye el proveedor (None vuelve al de la configuración)."""
    _OVERRIDE["provider"] = provider


def get_provider(settings) -> LLMProvider:
    if _OVERRIDE["provider"] is not None:
        return _OVERRIDE["provider"]
    if settings.ai_fake:
        return _FAKE
    if not settings.OPENROUTER_API_KEY:
        raise LLMError("auth", None, None, "falta OPENROUTER_API_KEY")
    proxy = settings.EGRESS_AI_URL or None
    return OpenRouterProvider(settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, proxy=proxy,
                              referer=settings.PUBLIC_WEB_URL, title=settings.APP_NAME)
