"""La prueba de carga k6 (tests/load) sigue a 16.1, al registro y a los umbrales de espera de 4.5 (D-146).

k6 no se ejecuta aquí (los números solo valen en el VPS, con la pila completa): se comprueba que el escenario pide lo que
dice 16.1, que las herramientas y opciones existen y son válidas, que las muestras las genera scripts/fixtures, que la
espera máxima es la de `Settings.queue_wait_limit` del grupo de cada herramienta y que el script es JavaScript válido.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "tests" / "load"
E = json.loads((LOAD / "escenarios.json").read_text(encoding="utf-8"))
SCRIPT = (LOAD / "k6.js").read_text(encoding="utf-8")


def _registry():
    from core.registry import load_registry

    return {s.slug_es: s for s in load_registry().specs}


def test_numeros_de_16_1():
    assert E["comprimir"]["herramienta"] == "comprimir-pdf" and E["comprimir"]["trabajos_simultaneos"] == 50
    assert E["audio"]["herramienta"] == "ogg-a-mp3" and E["audio"]["trabajos_simultaneos"] == 10
    assert (E["pico"]["trabajos"], E["pico"]["minutos"], E["pico"]["clientes"]) == (300, 5, 100)
    assert E["umbrales"]["pagina_ms"] == 1000


@pytest.mark.parametrize("scenario", ["comprimir", "audio", "pico"])
def test_herramienta_de_servidor_ligera_con_opciones_validas(scenario):
    from core.jobs import validate_options

    spec = _registry()[E[scenario]["herramienta"]]
    assert spec.where != "client", "la carga se mide en los workers"
    if scenario == "pico":
        assert spec.cost_class == "light", "el pico de 16.1 es de trabajos ligeros"
    validate_options(spec, E[scenario]["opciones"])  # INVALID_OPTIONS si una opción no existe o está fuera de rango


def test_muestras_de_scripts_fixtures():
    source = (ROOT / "scripts" / "fixtures" / "generate.py").read_text(encoding="utf-8")
    generated = set(re.findall(r'"([\w-]+\.\w+)": ', source))
    for scenario in ("comprimir", "audio", "pico"):
        assert E[scenario]["muestra"] in generated


def test_espera_maxima_por_grupo_igual_que_4_5():
    from core.settings import Settings

    specs = _registry()
    settings = Settings()
    groups = {E[s]["herramienta"]: specs[E[s]["herramienta"]].worker_group for s in ("comprimir", "audio", "pico")}
    for tool, group in groups.items():
        assert E["umbrales"]["espera_cola_s"][group] == settings.queue_wait_limit(group), tool
        # k6.js etiqueta la espera con el grupo de cada herramienta.
        assert f'"{tool}": "{group}"' in SCRIPT


def test_rutas_de_las_paginas_existen():
    specs = _registry()
    for route in E["paginas"]["rutas"]:
        locale, *rest = route.strip("/").split("/")
        assert locale in ("es", "en")
        if rest:
            slug = rest[0]
            assert any((s.slug_es if locale == "es" else s.slug_en) == slug for s in specs.values()), route


def test_el_script_usa_el_escenario_y_falla_con_el_limitador():
    assert 'open("./escenarios.json")' in SCRIPT
    for name in ("comprimir", "audio", "ligero", "paginas"):
        assert re.search(rf"export function {name}\(", SCRIPT), name
    # QUEUE_FULL es la respuesta buena a la saturación (503 con ese código); RATE_LIMITED invalida la prueba.
    assert 'res.status === 503 && code === "QUEUE_FULL"' in SCRIPT
    assert 'rate_limited: ["count==0"]' in SCRIPT
    assert 'dropped_iterations: ["count==0"]' in SCRIPT
    # QUOTA_EXCEEDED se cuenta aparte del limitador, para saber qué límite faltó subir.
    assert 'errorCode(res) === "QUOTA_EXCEEDED"' in SCRIPT
    assert 'cuota_superada: ["count==0"]' in SCRIPT


def test_cada_trabajo_es_nuevo():
    """Mismo propietario, herramienta, opciones y archivo = el mismo trabajo (idempotencia, 5.2): no llega a la cola."""
    body = SCRIPT.split("function runJob(", 1)[1].split("\n}\n", 1)[0]
    assert body.lstrip().split("\n")[2].strip() == "if (!newAnonSession()) return;"
    session = SCRIPT.split("function newAnonSession()", 1)[1].split("\n}\n", 1)[0]
    assert "token = null;" in session and "if (token) return token" not in session
    # Y si vuelve a aparecer un id ya visto, la prueba falla.
    assert "seenJobs.has(job.id)" in body
    assert 'trabajos_reutilizados: ["count==0"]' in SCRIPT


def _duration_s(value: str) -> int:
    m = re.fullmatch(r"(\d+)(s|m)", value)
    assert m, value
    return int(m[1]) * (60 if m[2] == "m" else 1)


def test_ninguna_espera_se_pierde_al_cortar_la_iteracion():
    """La espera que pasa del umbral se anota durante el sondeo, y cada escenario deja terminar al trabajo más lento."""
    loop = SCRIPT.split("function waitForJob(", 1)[1].split("\n}\n", 1)[0]
    assert "elapsed > limitMs" in loop and "queueWait.add(elapsed" in loop
    assert 'fail("tiempo")' in loop and 'fail("sondeo")' in loop and "E.sondeos_fallidos_max" in loop
    assert "gracefulStop: `${deadlineMs(E.pico.herramienta) / 1000 + 60}s`" in SCRIPT
    specs = _registry()
    for scenario in ("comprimir", "audio", "pico"):
        group = specs[E[scenario]["herramienta"]].worker_group
        deadline = E["umbrales"]["espera_cola_s"][group] + E["proceso_max_s"]
        if scenario != "pico":  # per-vu-iterations: maxDuration
            assert deadline < _duration_s(E["duracion_maxima"]), scenario
    assert E["sondeos_fallidos_max"] >= 2


def test_limites_documentados_cubren_el_escenario_desde_una_ip():
    """Desde una IP: sesiones anónimas, tareas del plan anon por IP (9.3) y peticiones por minuto."""
    from core.jobs import validate_options
    from core.plans import load_plans_file
    from core.settings import Settings

    limits = E["limites_durante_la_prueba"]
    specs = _registry()
    jobs = {"light": 0, "heavy": 0}
    for scenario, count in (("comprimir", E["comprimir"]["trabajos_simultaneos"]),
                            ("audio", E["audio"]["trabajos_simultaneos"]), ("pico", E["pico"]["trabajos"])):
        spec = specs[E[scenario]["herramienta"]]
        options, _ = validate_options(spec, E[scenario]["opciones"])
        jobs[spec.cost_for(options)] += count
    total = jobs["light"] + jobs["heavy"]
    assert total == 360
    # Una sesión por trabajo.
    assert limits["ANON_TOKENS_PER_IP_DAY"] >= total > Settings().ANON_TOKENS_PER_IP_DAY
    anon = load_plans_file(ROOT / "config" / "plans.yaml")["anon"]
    assert limits["anon.light_tasks_day"] >= jobs["light"] > anon.light_tasks_day
    assert jobs["heavy"] <= anon.heavy_tasks_day
    # Peticiones por minuto: cada VU a la vez sondea cada `sondeo_s` (más sesión, subida y creación).
    vus = E["comprimir"]["trabajos_simultaneos"] + E["audio"]["trabajos_simultaneos"] + E["pico"]["clientes"]
    assert limits["RATE_LIMIT_PER_MINUTE"] >= vus * (60 / E["sondeo_s"] + 10)

    # Y los pasos de OPERATIONS.md y DEPLOY-CHECKLIST ponen esos valores y devuelven después los de producción.
    ops = (ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")
    section = ops.split("## Prueba de carga", 1)[1].split("\n## ", 1)[0]
    assert f"RATE_LIMIT_PER_MINUTE={limits['RATE_LIMIT_PER_MINUTE']}" in section
    assert f"ANON_TOKENS_PER_IP_DAY={limits['ANON_TOKENS_PER_IP_DAY']}" in section
    raise_sql = f"jsonb_set(limits, '{{light_tasks_day}}', '{limits['anon.light_tasks_day']}') WHERE id = 'anon'"
    restore_sql = f"jsonb_set(limits, '{{light_tasks_day}}', '{anon.light_tasks_day}') WHERE id = 'anon'"
    assert raise_sql in section and restore_sql in section
    checklist = (ROOT / "docs" / "DEPLOY-CHECKLIST.md").read_text(encoding="utf-8")
    assert f"`light_tasks_day` del plan `anon` ({anon.light_tasks_day})" in checklist


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para comprobar la sintaxis del script")
def test_k6_js_es_javascript_valido(tmp_path):
    copy = tmp_path / "k6.mjs"  # módulo ES, como lo carga k6
    copy.write_text(SCRIPT, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
