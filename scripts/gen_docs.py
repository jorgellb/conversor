"""Genera docs/ERRORS.md (códigos estables y mensajes) y docs/TOOLS.md (catálogo, desactivadas con su motivo, 7.24 y
paridad con PDF24) desde el código, el registro y config/. `--check` falla si no están al día."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core"), str(ROOT / "packages/tools")]

from core.errors import MESSAGES, ErrorCode  # noqa: E402


def errors() -> str:
    lines = ["# Códigos de error (5.3)", "",
             "Códigos estables que devuelven la API (`error.code`) y las herramientas de navegador. Generado por "
             "`scripts/gen_docs.py` desde `packages/core/core/errors.py`.", "",
             "| Código | Mensaje (es) | Mensaje (en) |", "| --- | --- | --- |"]
    for code in ErrorCode:
        es = MESSAGES.get(code, {}).get("es", "")
        en = MESSAGES.get(code, {}).get("en", "")
        lines.append(f"| `{code}` | {es} | {en} |")
    return "\n".join(lines) + "\n"


WHERE = {"client": "navegador", "server": "servidor", "hybrid": "híbrida"}


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8")) or {}


def _static_pages() -> set[str]:
    text = (ROOT / "apps/web/src/lib/site.ts").read_text(encoding="utf-8")
    block = text[text.index("STATIC_PAGES"):text.index("} as const")]
    return set(re.findall(r'es: "([^"]+)"', block))


CONTENT_DIR = "apps/web/content/es"


def _git(*args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], input=stdin, capture_output=True, check=True).stdout


def _content_files() -> dict[str, bytes]:
    """Archivos de contenido en español tal como están en el índice de git (lo que va a entrar en el commit), no en el
    árbol de trabajo: los que otro lote en paralelo aún no ha añadido no cuentan, así `docs/TOOLS.md` coincide con el
    árbol de su propio commit. Sin repositorio (por ejemplo, un `git archive` extraído), se leen del disco."""
    try:
        top = Path(_git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        top = None
    if top != ROOT.resolve():
        return {f.stem: f.read_bytes() for f in (ROOT / CONTENT_DIR).glob("*.json")}
    paths = [p for p in _git("ls-files", "-z", "--", f"{CONTENT_DIR}/*.json").decode().split("\0")
             if p and Path(p).parent.as_posix() == CONTENT_DIR]
    if not paths:
        return {}
    out = _git("cat-file", "--batch", stdin="".join(f":{p}\n" for p in paths).encode())
    files, pos = {}, 0
    for p in paths:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise SystemExit(f"git cat-file no devuelve {p}: {out[pos:header_end].decode(errors='replace')}")
        size = int(header[2])
        files[Path(p).stem] = out[header_end + 1:header_end + 1 + size]
        pos = header_end + 1 + size + 1
    return files


def _content() -> dict[str, str]:
    content = {}
    for stem, raw in _content_files().items():
        page = json.loads(raw.decode("utf-8"))
        content[stem] = "revisado" if page.get("reviewed") else ("redactado, sin revisar" if page.get("complete") else "incompleto")
    return content


def _off_reasons(data: dict, notes: dict) -> dict[str, str]:
    """Herramientas apagadas en un despliegue con los valores por defecto, con su motivo (01-1, regla 7)."""
    from core.flags import THEMATIC_FLAGS, THEMATIC_TOOLS

    temas = notes.get("temas") or {}
    per_tool = notes.get("herramientas") or {}
    reasons: dict[str, str] = {}
    for flag, slugs in THEMATIC_TOOLS.items():
        if slugs and not temas.get(flag):
            raise SystemExit(f"config/tools-notes.yaml: falta el motivo del flag temático {flag}")
        if THEMATIC_FLAGS.get(flag):
            continue
        for slug in slugs:
            reasons[slug] = f"Apagada mientras `{flag}` no esté a `true`. {temas[flag]}"
    for t in data["tools"]:
        if t.get("default_enabled", True):
            continue
        reason = per_tool.get(t["slug_es"])
        if not reason:
            raise SystemExit(f"config/tools-notes.yaml: falta el motivo de {t['slug_es']}, apagada por defecto (D-134)")
        flag = "TOOL_" + t["slug_es"].upper().replace("-", "_") + "_ENABLED"
        reasons[t["slug_es"]] = f"Apagada por defecto; se enciende con `{flag}=true`. {reason}"
    return reasons


def _phase_counts(data: dict) -> str:
    counts: dict[str, int] = {}
    for t in data["tools"]:
        counts[t["phase"]] = counts.get(t["phase"], 0) + 1
    return ", ".join(f"{phase} {n}" for phase, n in sorted(counts.items()))


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _phase_status(notes: dict) -> str:
    """Fases cerradas y en curso, de `fases:` en config/tools-notes.yaml (la actualizan los lotes de cierre)."""
    fases = notes.get("fases") or {}
    closed = [str(x) for x in fases.get("cerradas") or []]
    current = [str(x) for x in fases.get("en_curso") or []]
    if not closed and not current:
        raise SystemExit("config/tools-notes.yaml: falta `fases:` con `cerradas` y `en_curso`")
    parts = []
    if closed:
        parts.append(f"Fases cerradas: {_join(closed)}")
    if current:
        parts.append(f"en curso: {_join(current)}")
    return "; ".join(parts) + "."


def _pdf24(data: dict, reasons: dict[str, str]) -> list[str]:
    registered = {t["slug_es"] for t in data["tools"]}
    pages = _static_pages()
    parity = _yaml("pdf24.yaml")
    lines = ["## Paridad con PDF24 (0.8, 7.23 y 17)", "",
             f"Cada herramienta web de tools.pdf24.org (lista revisada el {parity['revisado']}, `config/pdf24.yaml`) y su "
             "equivalente aquí. La paridad es de funciones: no se copian textos, diseños, plantillas ni marca. Al cerrar F6 "
             "no puede quedar ninguna fila «pendiente» sin su fase ni ninguna «sin equivalente» sin explicación (17).", "",
             "| PDF24 | Equivalente | Estado | Nota |", "| --- | --- | --- | --- |"]
    totals = {"disponible": 0, "pendiente": 0, "sin equivalente": 0}
    for row in parity["herramientas"]:
        eq = [str(x) for x in row.get("equivalentes") or []]
        fixed = [str(x) for x in row.get("paginas") or []]
        note = row.get("nota", "")
        missing, phases = [], set()
        for item in eq:
            slug, _, phase = item.partition(":")
            if phase and slug in registered:
                raise SystemExit(f"config/pdf24.yaml: {slug} ya está en el registro; quita «:{phase}» de su fila")
            if slug not in registered:
                if not phase:
                    raise SystemExit(f"config/pdf24.yaml: {slug} no está en el registro y no dice en qué fase llega")
                missing.append(slug)
                phases.add(phase)
        for page in fixed:
            if page not in pages:
                raise SystemExit(f"config/pdf24.yaml: la página fija {page} no está en STATIC_PAGES")
        if not eq and not fixed:
            if not note:
                raise SystemExit(f"config/pdf24.yaml: {row['pdf24']} no tiene equivalente ni explicación")
            state = "sin equivalente"
        elif missing:
            state = "pendiente"
        else:
            state = "disponible"
        totals[state] += 1
        shown = [f"`{x.partition(':')[0]}`" for x in eq] + [f"`{x}` (página fija)" for x in fixed]
        label = state
        if state == "pendiente":
            label = f"pendiente ({', '.join(sorted(phases))})"
        elif state == "disponible" and any(x.partition(":")[0] in reasons for x in eq):
            label = "disponible, apagada (ver «Desactivadas»)"
        lines.append(f"| {row['pdf24']} (`{row['ruta']}`) | {', '.join(shown) or '—'} | {label} | {note} |")
    lines += ["", f"Resumen: {totals['disponible']} disponibles, {totals['pendiente']} pendientes de su fase y "
              f"{totals['sin equivalente']} sin equivalente (con su explicación).", ""]
    return lines


def tools() -> str:
    data = json.loads((ROOT / "packages/registry/registry.json").read_text(encoding="utf-8"))
    notes = _yaml("tools-notes.yaml")
    content = _content()
    reasons = _off_reasons(data, notes)
    lines = ["# Herramientas (7, 7.24 y 17)", "",
             f"Catálogo publicado en esta entrega: {len(data['tools'])} herramientas ({_phase_counts(data)}). "
             f"{_phase_status(notes)} El orden y los lotes que faltan están en `docs/PLAN.md` y `docs/GOAL.md`. "
             "Generado por `scripts/gen_docs.py` desde `packages/registry/registry.json`, `config/tools-notes.yaml` y "
             "`config/pdf24.yaml`: no lo edites a mano.", "",
             "«Estado» es el de un despliegue con los valores por defecto: `TOOL_<SLUG>_ENABLED=false` apaga cualquiera y "
             "la tabla `feature_flags` también (5.2). «Indexable» exige herramienta activa, pruebas en verde y contenido propio "
             "completo y revisado en el idioma (7.22); sin él, la página lleva `noindex`.", "",
             "| Herramienta (es / en) | Dónde | Grupo | Coste | Fase | Estado | Entrada → salida | Contenido propio |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t in data["tools"]:
        state = "apagada" if t["slug_es"] in reasons else "activa"
        if t.get("canonical_of"):
            state += f", alias de `{t['canonical_of']}`"
        page = "no aplica (alias)" if t.get("canonical_of") else content.get(t["slug_es"], "pendiente")
        lines.append(f"| `{t['slug_es']}` / `{t['slug_en']}` | {WHERE[t['where']]} | {t['worker_group'] or '—'} | "
                     f"{t['cost_class']} | {t['phase']} | {state} | {', '.join(t['inputs']) or '—'} → "
                     f"{', '.join(t['outputs']) or 'pantalla'} | {page} |")
    lines += ["", "## Desactivadas y por qué (01-1, regla 7)", ""]
    if reasons:
        lines += ["| Herramienta | Motivo |", "| --- | --- |"]
        lines += [f"| `{slug}` | {reason} |" for slug, reason in sorted(reasons.items())
                  if slug in {t["slug_es"] for t in data["tools"]}]
        future = sorted(slug for slug in reasons if slug not in {t["slug_es"] for t in data["tools"]})
        if future:
            lines += ["", "Además, cuando lleguen a su fase: " + ", ".join(f"`{s}`" for s in future) +
                      " (mismo motivo que su flag temático)."]
    else:
        lines.append("Ninguna.")
    lines += ["", "## Fuera de alcance (7.24)", "", "| Qué | Por qué | Cómo sería posible |", "| --- | --- | --- |"]
    for item in notes.get("fuera_de_alcance") or []:
        lines.append(f"| {item['formato']} | {item['motivo']} | {item['posible']} |")
    lines += [""] + _pdf24(data, reasons)
    lines += ["## Mejoras posteriores", ""] + [f"- {m}" for m in notes.get("mejoras") or []]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    outputs = {ROOT / "docs" / "ERRORS.md": errors(), ROOT / "docs" / "TOOLS.md": tools()}
    if "--check" in argv:
        stale = [p.name for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"{', '.join(stale)} no está al día: ejecuta python scripts/gen_docs.py", file=sys.stderr)
            return 1
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    print("docs/ERRORS.md y docs/TOOLS.md generados")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
