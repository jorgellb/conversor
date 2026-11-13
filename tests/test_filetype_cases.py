"""Casos de detección por bytes compartidos con el detector del navegador (client-tools/src/filetype.ts, F5 lote F)."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.filetype import detect

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "fixtures" / "filetype-cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_server_detector_matches_the_shared_cases(case, tmp_path):
    path = tmp_path / f"muestra.{case['declared']}"
    path.write_bytes(base64.b64decode(case["b64"]))
    found = detect(path, case["declared"])
    assert (found.ext if found else None) == case["expected"]


def test_shared_cases_are_up_to_date():
    res = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "fixtures" / "filetype_cases.py"), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
