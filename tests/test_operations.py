"""Operación y seguridad de F1 (16.2, 16.4 y 16.7)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest

from helpers import auth

pytestmark = pytest.mark.integration


def _job(session, **kw):
    from core.jobs import utcnow
    from core.models import Job

    values = dict(owner_type="anon", owner_id=str(uuid.uuid4()), tool="comprimir-pdf", options={}, status="succeeded",
                  worker_group="pdf", queue="pdf", priority=5, cost_class="light", idempotency_key=uuid.uuid4().hex,
                  expires_at=utcnow() + timedelta(hours=1))
    values.update(kw)
    job = Job(**values)
    session.add(job)
    session.flush()
    return job


def test_cleanup_removes_expired_jobs_and_rejected_uploads(services):
    from core.db import session_scope
    from core.jobs import utcnow
    from core.maintenance import cleanup_expired
    from core.models import Job, Upload
    from core.storage import Store

    store = Store(services["files"])
    with session_scope() as s:
        job = _job(s, expires_at=utcnow() - timedelta(minutes=1))
        job_id = str(job.id)
        up = Upload(id=uuid.uuid4().hex, owner_type="anon", owner_id="x", tool="comprimir-pdf", path="", size=1,
                    reserved_bytes=0, original_name="a.pdf", state="rejected", expires_at=utcnow() + timedelta(hours=1))
        s.add(up)
        upload_id = up.id
    store.ensure_job_dirs(job_id)
    (store.out_dir(job_id) / "resultado.pdf").write_bytes(b"%PDF-1.7")
    store.upload_path(upload_id).write_bytes(b"x")
    counts = cleanup_expired()
    assert counts["jobs"] >= 1 and counts["uploads"] >= 1
    assert not store.job_dir(job_id).exists()
    assert not store.upload_path(upload_id).exists()
    with session_scope() as s:
        assert s.get(Job, job_id).status == "expired"
        assert s.get(Upload, upload_id) is None


def test_find_orphans_removes_directories_without_job(services):
    from core.maintenance import find_orphans
    from core.storage import Store

    store = Store(services["files"])
    orphan = str(uuid.uuid4())
    store.ensure_job_dirs(orphan)
    old = time.time() - 7200
    os.utime(store.job_dir(orphan), (old, old))
    assert find_orphans()["removed_dirs"] >= 1
    assert not store.job_dir(orphan).exists()


def test_disk_guard_rejects_new_uploads(anon_token, tus_upload, fixtures_dir, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "DISK_MAX_USAGE_PERCENT", 0.0)
    uid, resp = tus_upload(anon_token(), "comprimir-pdf", fixtures_dir / "texto.pdf")
    assert uid is None and resp["HTTPResponse"]["StatusCode"] == 503
    assert json.loads(resp["HTTPResponse"]["Body"])["error"]["code"] == "DISK_FULL"


def test_disk_reservation_stops_overcommit(services):
    from core import disk
    from core.valkey import get_valkey

    r = get_valkey()
    root = Path(services["files"])
    free_gb = shutil.disk_usage(root).free / disk.GB - disk.reserved_bytes(r) / disk.GB
    size = 100 * 1024 * 1024
    # Deja sitio para una reserva de 300 MB (100 MB × factor 3) pero no para dos.
    min_free = free_gb - (size * 3 * 1.5) / disk.GB
    assert disk.try_reserve(r, root, "prueba-1", size, 3.0, 100.0, min_free)
    assert not disk.try_reserve(r, root, "prueba-2", size, 3.0, 100.0, min_free)
    disk.release(r, "prueba-1")


def test_worker_lost_after_three_attempts_without_loops(services, monkeypatch):
    from core import maintenance
    from core.db import session_scope
    from core.jobs import utcnow
    from core.models import Job

    sent = []
    monkeypatch.setattr(maintenance.celery_app, "send_task", lambda *a, **kw: sent.append((a, kw)))
    stale = utcnow() - timedelta(minutes=10)
    with session_scope() as s:
        dead = _job(s, status="running", attempts=3, heartbeat_at=stale).id
        retry = _job(s, status="running", attempts=1, heartbeat_at=stale).id
        secret = _job(s, tool="desbloquear-pdf", status="running", attempts=1, heartbeat_at=stale, has_secrets=True).id
    maintenance.requeue_stale()
    with session_scope() as s:
        assert (s.get(Job, dead).status, s.get(Job, dead).error_code) == ("failed", "WORKER_LOST")
        assert s.get(Job, retry).status == "queued"
        assert (s.get(Job, secret).status, s.get(Job, secret).error_code) == ("failed", "WORKER_LOST")
    assert [kw["args"][1] for _, kw in sent if kw["args"][0] == str(retry)] == [2]
    assert all(kw["args"][2] == "" for _, kw in sent)


def test_duplicate_delivery_runs_once(services):
    """Un mensaje repetido (p. ej. tras `visibility_timeout`) con un intento ya usado no vuelve a ejecutar el trabajo."""
    from core.db import session_scope
    from core.jobs import start_attempt

    with session_scope() as s:
        job_id = str(_job(s, status="queued", attempts=0).id)
    with session_scope() as s:
        assert start_attempt(s, job_id, 1)
    with session_scope() as s:
        assert not start_attempt(s, job_id, 1)


def test_enqueued_task_args_never_contain_secrets(api, user_token, tus_upload, fixtures_dir, monkeypatch):
    from app.routers import jobs as jobs_router
    from core.celeryapp import celery_app

    sent = []
    monkeypatch.setitem(jobs_router.ENQUEUE, "fn", None)
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: sent.append(kw))
    token = user_token()
    uid, _ = tus_upload(token, "desbloquear-pdf", fixtures_dir / "cifrado.pdf", filename="secreto.pdf")
    resp = api.post("/v1/jobs", json={"tool": "desbloquear-pdf", "upload_ids": [uid], "options": {"contrasena": "secreto123"}},
                    headers=auth(token))
    assert resp.status_code == 201, resp.text
    assert sent and "secreto123" not in json.dumps(sent)
    assert sent[0]["args"][2].startswith("v1.")


def test_anon_tokens_limited_per_ip(api, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setattr(get_settings(), "ANON_TOKENS_PER_IP_DAY", 2)
    headers = {"X-Forwarded-For": "198.51.100.77"}
    codes = [api.post("/v1/session/anon", json={"turnstile_token": "ok"}, headers=headers).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_cf_connecting_ip_only_from_cloudflare():
    from core.clientip import real_ip

    # Petición que llega a Traefik desde Cloudflare: se usa CF-Connecting-IP.
    via_cf = {"x-forwarded-for": "203.0.113.5, 173.245.48.10", "cf-connecting-ip": "203.0.113.5"}
    assert real_ip("172.18.0.4", via_cf, trust_cf=True) == "203.0.113.5"
    # Alguien llega directo al origen y falsifica la cabecera: se usa su IP real.
    spoof = {"x-forwarded-for": "198.51.100.20", "cf-connecting-ip": "1.2.3.4"}
    assert real_ip("172.18.0.4", spoof, trust_cf=True) == "198.51.100.20"
    # Sin confiar en Cloudflare, nunca se mira la cabecera.
    assert real_ip("172.18.0.4", via_cf, trust_cf=False) == "173.245.48.10"


def test_run_engine_timeout_kills_process_group(tmp_path):
    from core.errors import ToolError
    from tools.base import run_engine

    marker = tmp_path / "hijo.pid"
    start = time.monotonic()
    with pytest.raises(ToolError) as err:
        run_engine(["sh", "-c", f"sleep 30 & echo $! > {marker}; wait"], tmp_path, timeout=1)
    assert err.value.code == "TIMEOUT"
    assert time.monotonic() - start < 10
    child = int(marker.read_text())
    time.sleep(0.2)
    assert not Path(f"/proc/{child}").exists() or "Z" in Path(f"/proc/{child}/stat").read_text().split()[2]


def test_run_engine_environment_has_no_secrets(tmp_path, monkeypatch):
    from tools.base import run_engine

    monkeypatch.setenv("FILE_TOKEN_SECRET", "no-debe-salir")
    out = run_engine(["env"], tmp_path, timeout=10).stdout.decode()
    assert "no-debe-salir" not in out and "FILE_TOKEN_SECRET" not in out


def test_zip_bomb_and_traversal_are_cut(tmp_path):
    from core.errors import ToolError
    from core.zipguard import check_zip

    bomb = tmp_path / "bomba.xlsx"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (60 * 1024 * 1024))
    with pytest.raises(ToolError) as err:
        check_zip(bomb)
    assert err.value.code == "LIMIT_EXCEEDED"
    evil = tmp_path / "rutas.docx"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../etc/cron.d/x", b"x")
    with pytest.raises(ToolError):
        check_zip(evil)


def test_giant_png_is_rejected_before_decoding(tmp_path):
    """PNG con cabecera de 50 000 × 50 000 píxeles: se rechaza por IMAGE_MAX_PIXELS sin descomprimirlo."""
    import struct
    import zlib

    from core.errors import ToolError
    from core.settings import get_settings
    from tools.pdf.imagenes_a_pdf import _image_bytes

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 50_000, 50_000, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"\x00" * 1000)) + chunk(b"IEND", b"")
    path = tmp_path / "gigante.png"
    path.write_bytes(png)
    with pytest.raises(ToolError) as err:
        _image_bytes(path, "png", get_settings().IMAGE_MAX_PIXELS)
    assert err.value.code == "LIMIT_EXCEEDED"


def test_backup_and_restore_roundtrip(services, tmp_path):
    from sqlalchemy import create_engine, text

    from app.ops.backup import dump
    from app.ops.restore import restore

    url = services["db_url"].replace("postgresql+psycopg", "postgresql")
    engine = create_engine(services["db_url"])
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS copia_prueba (v text)"))
        conn.execute(text("DELETE FROM copia_prueba"))
        conn.execute(text("INSERT INTO copia_prueba VALUES ('antes')"))
    file = dump(url, tmp_path)
    assert file.exists() and file.stat().st_size > 0
    with engine.begin() as conn:
        conn.execute(text("UPDATE copia_prueba SET v = 'despues'"))
    restore(url, file)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT v FROM copia_prueba")).scalar_one() == "antes"
        conn.execute(text("DROP TABLE copia_prueba"))
    engine.dispose()


@pytest.mark.skipif(shutil.which("restic") is None, reason="restic no instalado (la CI lo prueba contra SFTP en contenedor)")
def test_restic_local_repository(tmp_path):
    from app.ops.backup import restic

    data = tmp_path / "datos"
    data.mkdir()
    (data / "a.txt").write_text("hola")
    repo = tmp_path / "repo"
    restic(str(repo), "clave-prueba", [data])
    env = {"PATH": os.environ["PATH"], "RESTIC_REPOSITORY": str(repo), "RESTIC_PASSWORD": "clave-prueba", "HOME": str(tmp_path)}
    out = subprocess.run(["restic", "snapshots", "--json"], env=env, capture_output=True, check=True).stdout
    assert json.loads(out)


def test_worker_role_has_only_its_tables(services, monkeypatch):
    """Rol limitado de los workers (9.4): escribe en jobs y no puede leer cuentas, pagos ni flags."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ProgrammingError

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "apps/api/alembic.ini"))
    cfg.set_main_option("script_location", str(root / "apps/api/migrations"))
    monkeypatch.setenv("WORKER_DB_PASSWORD", "clave-del-worker")
    command.downgrade(cfg, "0001_inicial")
    command.upgrade(cfg, "head")
    url = make_url(services["db_url"]).set(username="conversor_worker", password="clave-del-worker")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT count(*) FROM jobs")).scalar()
        conn.execute(text("SELECT count(*) FROM plans")).scalar()
        for table in ("subscriptions", "stripe_events", "feature_flags", "anon_clients", "audit_log"):
            with pytest.raises(ProgrammingError):
                conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            conn.rollback()
        with pytest.raises(ProgrammingError):
            conn.execute(text("UPDATE plans SET name = name"))
        conn.rollback()
        # F4 (D-188): el registro del sello solo se lee y se añade; las solicitudes de firma son de la API.
        conn.execute(text("INSERT INTO seal_signatures (job_id, document_sha256, level) "
                          "VALUES ('00000000-0000-0000-0000-000000000001', 'x', 'B-B')"))
        conn.execute(text("SELECT count(*) FROM seal_signatures")).scalar()
        for statement in ("UPDATE seal_signatures SET level = level", "DELETE FROM seal_signatures",
                          "SELECT 1 FROM signature_requests", "SELECT 1 FROM signers", "SELECT 1 FROM audit_events"):
            conn.rollback()
            with pytest.raises(ProgrammingError):
                conn.execute(text(statement))
        conn.rollback()
    engine.dispose()


def test_run_engine_stack_limit_lets_many_threads_fit_in_data_limit(tmp_path):
    """D-269: las pilas de los hilos cuentan en RLIMIT_DATA y glibc les da RLIMIT_STACK (8 MB de serie). Con 60 hilos y
    300 MB de datos no caben con 8 MB por hilo; con `stack_mb=2`, sí (es lo que pasaba con SVT-AV1 1.7 en Ubuntu 24.04)."""
    import sys

    from core.errors import ToolError
    from tools.base import run_engine

    code = ("import threading\nev = threading.Event()\nts = [threading.Thread(target=ev.wait) for _ in range(60)]\n"
            "try:\n    [t.start() for t in ts]\nfinally:\n    ev.set()\nprint('ok')")
    out = run_engine([sys.executable, "-I", "-c", code], tmp_path, timeout=30, mem_mb=300, limit_data=True, stack_mb=2)
    assert out.stdout.strip() == b"ok"
    assert run_engine(["sh", "-c", "ulimit -s"], tmp_path, timeout=10, stack_mb=2).stdout.strip() == b"2048"
    with pytest.raises(ToolError) as err:
        run_engine([sys.executable, "-I", "-c", code], tmp_path, timeout=30, mem_mb=300, limit_data=True, stack_mb=8)
    assert err.value.code == "ENGINE_FAILED"


def test_ffmpeg_calls_with_data_limit_set_small_stack():
    """Toda llamada a FFmpeg con límite de datos fija la pila (D-269)."""
    import ast

    root = Path(__file__).resolve().parents[1] / "packages/tools/tools"
    checked = 0
    for f in [root / "av/video.py", root / "av/video_edicion.py", root / "office/diapositivas.py"]:
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "run_engine":
                kw = {k.arg for k in node.keywords}
                if "limit_data" in kw:
                    checked += 1
                    assert "stack_mb" in kw, f"{f.name}:{node.lineno} sin stack_mb"
    assert checked >= 5
