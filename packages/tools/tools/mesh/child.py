"""Proceso hijo de las conversiones de mallas (D-249): `python -I child.py trabajo.json`.

Recibe las rutas del código (con `-I` no se lee PYTHONPATH), el archivo y las opciones; escribe `resultado.json` con los
archivos creados o el error. Códigos: 0, bien; 2, error de la herramienta (en el JSON); 5, sin memoria.
"""
import json
import sys


class _Input:
    def __init__(self, item: dict):
        from pathlib import Path

        self.path = Path(item["path"])
        self.name = item["name"]
        self.ext = item["ext"]
        self.size = int(item["size"])


class _Context:
    """Lo que usan del ToolContext las herramientas que se ejecutan enteras en el hijo (G-code, D-258): entradas, opciones,
    idioma y `output`, que da nombres únicos dentro de la carpeta de salida (el padre los mueve a su sitio)."""

    def __init__(self, job: dict, options):
        from pathlib import Path

        self.tool = job["tool"]
        self.locale = job["locale"]
        self.options = options
        self.inputs = [_Input(i) for i in job["inputs"]]
        self.out_dir = Path(job["out_dir"])
        self._used: set[str] = set()

    def report(self, *_args, **_kw) -> None:
        return None

    def output(self, display_name: str):
        import re

        base = re.sub(r"[\x00-\x1f/\\]", "_", display_name).strip(". ")[:120] or "archivo"
        stem, dot, ext = base.rpartition(".")
        if not dot:
            stem, ext = base, ""
        name, n = base, 2
        while name in self._used:
            name = f"{stem}-{n}.{ext}" if ext else f"{stem}-{n}"
            n += 1
        self._used.add(name)
        return self.out_dir / name


def _call(job: dict) -> list[dict]:
    from importlib import import_module

    module, cls = job["options_class"].split(":")
    options = getattr(import_module(module), cls).model_validate(job["options"])
    module, fn = job["call"].split(":")
    outputs = getattr(import_module(module), fn)(_Context(job, options))
    return [{"file": o["path"], "name": o["name"], "note": o.get("note", "")} for o in outputs]


def main(job_path: str) -> int:
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    sys.path[:0] = job["paths"]
    from pathlib import Path

    from core.errors import ToolError
    from tools.mesh.pipeline import GEN_TOOLS, OP_TOOLS, convert_file, generate_file, join_files, operate_file

    result_path = Path(job["result"])
    try:
        if job.get("call"):
            outputs = _call(job)
            result_path.write_text(json.dumps({"outputs": outputs}), encoding="utf-8")
            return 0
        args = (job["options"], job["locale"], int(job["max_triangles"]), job["stem"], Path(job["out_dir"]))
        if job.get("srcs"):
            outputs = join_files([(Path(a), b, c) for a, b, c in job["srcs"]], *args)
        elif job["tool"] in GEN_TOOLS:
            outputs = generate_file(Path(job["src"]) if job.get("src") else None, job["ext"], job["tool"], *args)
        elif job["tool"] in OP_TOOLS:
            outputs = operate_file(Path(job["src"]), job["ext"], job["tool"], *args)
        else:
            outputs = convert_file(Path(job["src"]), job["ext"], job["tool"], *args)
    except ToolError as exc:
        result_path.write_text(json.dumps({"error": {"code": str(exc.code), "detail": exc.detail}}), encoding="utf-8")
        return 2
    except MemoryError:
        return 5
    except Exception as exc:  # noqa: BLE001 - lib3mf o trimesh con un archivo raro: error de la herramienta, no traza
        text = f"{type(exc).__name__}: {exc}"
        if "alloc" in text.lower() or "memory" in text.lower():
            return 5
        result_path.write_text(json.dumps({"error": {"code": "CORRUPT_FILE", "detail": text[:300]}}), encoding="utf-8")
        return 2
    result_path.write_text(json.dumps({"outputs": outputs}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
