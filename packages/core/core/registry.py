"""Registro central de herramientas (sección 5.2).

Solo contiene especificaciones: slugs, opciones, límites y fase. Importar este módulo
no carga motores; las implementaciones se importan por nombre en los workers.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

Where = Literal["client", "server", "hybrid"]
CostClass = Literal["light", "heavy", "ai"]


class NoOptions(BaseModel):
    """Herramienta sin opciones propias."""


@dataclass(frozen=True)
class AiSpec:
    """Lo que una herramienta de IA pide al modelo (6.2) y cuántas peticiones reserva al encolar (6.3).

    `estimate` recibe las opciones y da el mínimo que se reserva en la API; el worker reserva el resto en cuanto conoce
    el texto, antes de hacer ninguna petición.
    """

    estimate: Callable[[dict], int] | None = None
    json: bool = False
    images: bool = False
    min_context: int = 8000
    min_output: int = 1000
    # Opción booleana que enciende la IA (imagen-a-excel, D-161): apagada, el trabajo no pide cuenta, consentimiento ni
    # peticiones. None: la herramienta siempre usa la IA.
    option: str | None = None
    # La estimación es por archivo (ticket-a-excel: 1 petición por ticket, 6.3).
    per_file: bool = False

    def used_by(self, options: dict) -> bool:
        """Si el trabajo con estas opciones puede llamar al modelo."""
        return self.option is None or bool(options.get(self.option, True))

    def requests_for(self, options: dict, files: int = 1) -> int:
        """Peticiones que se reservan al encolar; 0 si el trabajo no llama al modelo (chat-pdf solo prepara)."""
        if not self.used_by(options):
            return 0
        n = max(0, int(self.estimate(options))) if self.estimate else 1
        return n * max(1, files) if self.per_file else n


@dataclass(frozen=True)
class ToolSpec:
    slug_es: str
    slug_en: str
    name_es: str
    name_en: str
    category: str
    where: Where
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    options: type[BaseModel] = NoOptions
    phase: str = "F1"
    worker_group: str | None = None
    cost_class: CostClass = "light"
    queue_kind: Literal["light", "heavy", "embed", "verify"] | None = None
    secret_fields: tuple[str, ...] = ()
    impl: str | None = None
    launch: bool = False
    indexable: bool = True
    max_files: int | None = None
    time_limit: int = 600
    summary_es: str = ""
    summary_en: str = ""
    related: tuple[str, ...] = field(default_factory=tuple)
    # Alias de otra herramienta (p. ej., pub-a-pdf): la página lleva `canonical` a esa y no entra en el sitemap.
    canonical_of: str | None = None
    # Enrutado opcional por opciones: devuelve (grupo, cola). P. ej., pdf-a-word «fiel» va a LibreOffice.
    route: Callable[[dict], tuple[str, str]] | None = None
    # Clase de coste según las opciones (convertir-desde-pdf: una imagen es ligera y un DOCX con Docling, pesado).
    cost: Callable[[dict], CostClass] | None = None
    # Herramientas de IA (F3): requisitos del modelo y estimación de peticiones.
    ai: AiSpec | None = None
    # Apagada por defecto (D-134): solo se enciende con `TOOL_<SLUG>_ENABLED=true` en el entorno, que leen la API y la
    # web. Para udf-a-pdf (7.23) y las herramientas sin muestra válida (01-1, regla 8). El motivo va en
    # config/tools-notes.yaml y sale en docs/TOOLS.md (regla 7).
    default_enabled: bool = True
    # Comprobación previa en la API antes de encolar (pdf-a-audio: caracteres por tarea de 9.3), como
    # «módulo:función». Recibe (settings, plan, owner_type, opciones, rutas de los archivos, locale=«es»|«en», el de la
    # página) y lanza AppError. Se importa solo al crear el trabajo, así que el registro sigue sin cargar motores.
    precheck: str | None = None
    # Vídeo (9.3): solo en planes con `video` (Pro). La API lo rechaza antes de encolar y la página lo avisa (D-241).
    needs_video: bool = False

    @property
    def slug(self) -> str:
        return self.slug_es

    @property
    def runs_on_server(self) -> bool:
        return self.where in ("server", "hybrid") and self.impl is not None

    def target(self, options: dict) -> tuple[str, str]:
        if self.route is not None:
            return self.route(options)
        return self.worker_group, self.queue

    def cost_for(self, options: dict) -> CostClass:
        return self.cost(options) if self.cost is not None else self.cost_class

    @property
    def queue(self) -> str | None:
        if not self.worker_group:
            return None
        if self.queue_kind:
            return f"{self.worker_group}.{self.queue_kind}"
        return self.worker_group

    def to_public(self) -> dict:
        schema = self.options.model_json_schema()
        for name in self.secret_fields:
            prop = schema.get("properties", {}).get(name)
            if prop is not None:
                prop["writeOnly"] = True
                prop["format"] = "password"
        return {
            "slug_es": self.slug_es,
            "slug_en": self.slug_en,
            "name_es": self.name_es,
            "name_en": self.name_en,
            "summary_es": self.summary_es,
            "summary_en": self.summary_en,
            "category": self.category,
            "where": self.where,
            "worker_group": self.worker_group,
            "cost_class": self.cost_class,
            # Límite diario de tareas que gasta con sus opciones por defecto (puede no coincidir con la clase: D-161).
            "task_class": self.cost_for({}),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "phase": self.phase,
            "launch": self.launch,
            "default_enabled": self.default_enabled,
            "indexable": self.indexable,
            "max_files": self.max_files,
            "needs_video": self.needs_video,
            "secret_fields": list(self.secret_fields),
            "related": list(self.related),
            "canonical_of": self.canonical_of,
            "ai": self.ai is not None,
            "ai_option": self.ai.option if self.ai is not None else None,
            "options_schema": schema,
        }


class Registry:
    def __init__(self, specs: list[ToolSpec]):
        self._by_slug: dict[str, ToolSpec] = {}
        for spec in specs:
            for slug in (spec.slug_es, spec.slug_en):
                if slug in self._by_slug and self._by_slug[slug] is not spec:
                    raise ValueError(f"Slug duplicado en el registro: {slug}")
                self._by_slug[slug] = spec
        self.specs = specs

    def get(self, slug: str) -> ToolSpec | None:
        return self._by_slug.get(slug)

    def require(self, slug: str) -> ToolSpec:
        spec = self.get(slug)
        if spec is None:
            from core.errors import AppError, ErrorCode

            raise AppError(ErrorCode.NOT_FOUND, status=404, detail=f"Herramienta desconocida: {slug}")
        return spec

    def server_tools(self) -> list[ToolSpec]:
        return [s for s in self.specs if s.runs_on_server]


SPEC_MODULES = (
    "tools.client.specs",
    "tools.pdf.specs",
    "tools.office.specs",
    "tools.ocr.specs",
    "tools.convert.specs",
    "tools.av.specs",
    "tools.media.specs",
    "tools.ai.specs",
    "tools.sign.specs",
    "tools.utils.specs",
)


@lru_cache
def load_registry() -> Registry:
    specs: list[ToolSpec] = []
    for module_name in SPEC_MODULES:
        module = importlib.import_module(module_name)
        specs.extend(module.SPECS)
    return Registry(specs)


def load_precheck(spec: ToolSpec):
    """La comprobación previa de la herramienta, o None si no tiene."""
    if not spec.precheck:
        return None
    module_name, _, func = spec.precheck.partition(":")
    return getattr(importlib.import_module(module_name), func)


def load_impl(spec: ToolSpec):
    """Importa la función `run` de la implementación. Solo se usa en los workers."""
    if not spec.impl:
        raise RuntimeError(f"{spec.slug_es} no tiene implementación de servidor")
    module_name, _, func = spec.impl.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, func or "run")
