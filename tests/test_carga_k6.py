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


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para comprobar la sintaxis del script")
def test_k6_js_es_javascript_valido(tmp_path):
    copy = tmp_path / "k6.mjs"  # módulo ES, como lo carga k6
    copy.write_text(SCRIPT, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
