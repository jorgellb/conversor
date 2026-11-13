"""Límites por plan (9.3). La fuente de verdad en producción es la tabla `plans`."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class PlanLimits(BaseModel):
    name: str
    # Identificador del plan (anon, free o pro): algunas opciones solo existen en Pro.
    id: str = ""
    light_tasks_day: int
    heavy_tasks_day: int
    files_per_task: int
    max_file_mb: int
    max_task_mb: int
    pdf_pages: int
    audio_minutes: int
    video: bool
    video_minutes: int
    mesh_triangles: int
    ai_requests_day: int
    ai_requests_task: int
    ai_pages_task: int
    tts_chars_task: int
    retention_hours: int
    share_days: int
    priority: int

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    @property
    def max_task_bytes(self) -> int:
        return self.max_task_mb * 1024 * 1024

    def tasks_for(self, cost_class: str) -> int:
        return self.heavy_tasks_day if cost_class == "heavy" else self.light_tasks_day


def load_plans_file(path: Path) -> dict[str, PlanLimits]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {pid: PlanLimits(**{**values, "id": pid}) for pid, values in data["plans"].items()}
