"""docker-compose.coolify.yml (13.2 y 5.4): generado al día, memoria y CPU sobreescribibles y dentro del 15 % de la RAM.

`docker compose config` (`--validate`) solo se puede ejecutar con Docker, en la CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_coolify_compose as gen  # noqa: E402

VAR = re.compile(r"^\$\{([A-Z0-9_]+):-([^}]+)\}$")


def _bytes(value: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([mg])", str(value))
    assert m, value
    return float(m.group(1)) * (1024 if m.group(2) == "g" else 1) / 1024  # GB


def _resolve(value, env: dict[str, str]) -> str:
    m = VAR.match(str(value))
    if not m:
        return str(value)
    return env.get(m.group(1), m.group(2))


def _doc() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))


def test_compose_up_to_date():
    assert gen.main(["--check"]) == 0


def test_workers_memory_and_cpu_overridable():
    workers = {name: s for name, s in _doc()["services"].items() if name.startswith("worker")}
    assert workers
    for name, service in workers.items():
        mem = VAR.match(service["mem_limit"])
        assert mem and mem.group(1).startswith("MEM_"), name
        assert service["memswap_limit"] == service["mem_limit"], name
        cpus = VAR.match(str(service["cpus"]))
        assert cpus and cpus.group(1) == "CPUS_" + mem.group(1).removeprefix("MEM_"), name
        assert any(part.startswith("${CONCURRENCY_" + mem.group(1).removeprefix("MEM_") + ":-") for part in service["command"]), name
    for name in ("postgres", "gotenberg", "gotenbergweb"):
        assert VAR.match(_doc()["services"][name]["mem_limit"]).group(1) == f"MEM_{name.upper()}"


def _total(env: dict[str, str]) -> float:
    return sum(_bytes(_resolve(s["mem_limit"], env)) for s in _doc()["services"].values() if "mem_limit" in s)


def test_memory_within_15_percent_of_ram():
    """5.4: la suma de mem_limit no supera la RAM en más de un 15 % (32 GB con 8 vCPU y 64 GB con 16 vCPU)."""
    assert _total({}) <= 32 * 1.15
    assert _total(gen.PROFILE_16) <= 64 * 1.15
    assert _total(gen.PROFILE_16) > _total({})


def test_profile_16_matches_compose_variables():
    text = (ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{((?:MEM|CPUS|CONCURRENCY)_[A-Z0-9_]+):-", text))
    assert set(gen.PROFILE_16) <= used
    # cpus = concurrencia × hilos (5.4) en el perfil de 16 vCPU.
    for name, service in _doc()["services"].items():
        if not name.startswith("worker"):
            continue
        cpu_var = VAR.match(str(service["cpus"])).group(1)
        suffix = cpu_var.removeprefix("CPUS_")
        threads = int(service["environment"]["THREADS"])
        conc = int(gen.PROFILE_16.get(f"CONCURRENCY_{suffix}", "0"))
        cpus = int(gen.PROFILE_16.get(cpu_var, "0"))
        assert conc and cpus == conc * threads, name


def test_profile_cli(capsys):
    assert gen.main(["--profile", "16"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert dict(line.split("=", 1) for line in lines) == gen.PROFILE_16
    assert gen.main(["--profile", "8"]) == 2
