"""Comprueba las licencias de las dependencias instaladas contra scripts/license_policy.yaml (11).

- Python: `pip-licenses` del entorno actual (en la CI, uno por imagen).
- npm: dependencias de producción de la web (`npm ls --omit=dev --all --json`) leyendo el campo `license`
  de cada package.json instalado, que es lo mismo que hace license-checker.
Falla ante una licencia fuera de lista, una desconocida o un paquete GPL o AGPL.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "scripts" / "license_policy.yaml").read_text(encoding="utf-8"))


def normalize(name: str, license_text: str) -> str:
    if name in POLICY["overrides"]:
        return POLICY["overrides"][name]
    text = (license_text or "").strip()
    return POLICY["aliases"].get(text, text)


def check(kind: str, name: str, version: str, license_text: str, problems: list[str]) -> None:
    allowed = set(POLICY[kind]["allowed"])
    lname = name.lower()
    if lname in POLICY["forbidden_packages"]:
        problems.append(f"{kind}: {name} {version} está prohibido (11)")
        return
    lic = normalize(lname, license_text)
    if any(p.lower() in lic.lower() for p in POLICY["forbidden_patterns"]) and "LGPL" not in lic and "Lesser" not in lic:
        problems.append(f"{kind}: {name} {version} tiene licencia GPL/AGPL ({lic})")
        return
    # Licencias compuestas «A OR B»: basta con que una opción esté permitida (se elige la permisiva).
    # «A AND B» (código de varias licencias en un paquete, como numpy): todas deben estar permitidas.
    options = [o.strip(" ()") for o in re.split(r"\s+OR\s+|;\s*", lic) if o.strip()]

    def ok(option: str) -> bool:
        parts = [POLICY["aliases"].get(p.strip(" ()"), p.strip(" ()")) for p in re.split(r"\s+AND\s+", option) if p.strip(" ()")]
        return bool(parts) and all(p in allowed for p in parts)

    if not options or not any(ok(o) for o in options):
        problems.append(f"{kind}: {name} {version} con licencia no permitida o desconocida: «{license_text}»")


CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0",
    "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)": "LGPL-2.1",
    "License :: OSI Approved :: GNU General Public License (GPL)": "GPL",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
}


def python_packages() -> list[tuple[str, str, str]]:
    """Licencia de cada distribución instalada: License-Expression (PEP 639), License o clasificadores."""
    from importlib import metadata

    found: dict[str, tuple[str, str, str]] = {}
    for dist in metadata.distributions():
        meta = dist.metadata
        name = meta.get("Name") or ""
        if not name or name.lower() in found:
            continue
        lic = (meta.get("License-Expression") or "").strip()
        raw = (meta.get("License") or "").strip()
        if not lic and raw and len(raw) < 80 and "\n" not in raw:
            lic = raw
        if not lic:
            mapped = sorted({CLASSIFIERS[c] for c in meta.get_all("Classifier") or [] if c in CLASSIFIERS})
            lic = " OR ".join(mapped)
        found[name.lower()] = (name, meta.get("Version") or "", lic or "UNKNOWN")
    return sorted(found.values())


def npm_packages(workspace: str) -> list[tuple[str, str, str]]:
    res = subprocess.run(["npm", "ls", "--omit=dev", "--all", "--json", "-w", workspace], cwd=ROOT, capture_output=True, text=True)
    tree = json.loads(res.stdout or "{}")
    found: dict[str, tuple[str, str, str]] = {}

    def walk(deps: dict) -> None:
        for name, info in (deps or {}).items():
            version = info.get("version", "")
            key = f"{name}@{version}"
            if key in found or info.get("extraneous"):
                continue
            pkg_json = None
            for base in (ROOT / "node_modules", ROOT / "apps" / "web" / "node_modules"):
                candidate = base / name / "package.json"
                if candidate.exists():
                    pkg_json = json.loads(candidate.read_text(encoding="utf-8"))
                    break
            lic = ""
            if pkg_json:
                raw = pkg_json.get("license") or pkg_json.get("licenses") or ""
                lic = raw.get("type", "") if isinstance(raw, dict) else raw if isinstance(raw, str) else ";".join(
                    (x.get("type", "") if isinstance(x, dict) else str(x)) for x in raw)
            if pkg_json is None:
                # Dependencias opcionales o de pares que no están instaladas: no se distribuyen.
                continue
            if name.startswith("@conversor/"):
                lic = "MIT"  # paquetes propios del monorepo
            found[key] = (name, version, lic)
            walk(info.get("dependencies", {}))

    walk(tree.get("dependencies", {}))
    return list(found.values())


def main(argv: list[str]) -> int:
    problems: list[str] = []
    scopes = argv or ["python", "npm"]
    if "python" in scopes:
        for name, version, lic in python_packages():
            if name.lower() in POLICY["dev_only"]:
                continue
            check("backend", name, version, lic, problems)
    if "npm" in scopes:
        for name, version, lic in npm_packages("@conversor/web"):
            if name in POLICY.get("not_bundled", []):
                continue  # sustituida al empaquetar (next.config.ts); la CI comprueba que no está en el build
            check("frontend", name, version, lic, problems)
    for p in problems:
        print(p, file=sys.stderr)
    print(f"Licencias: {len(problems)} problema(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
