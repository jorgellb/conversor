"""Proceso hijo de las conversiones de mallas (D-249): `python -I child.py trabajo.json`.

Recibe las rutas del código (con `-I` no se lee PYTHONPATH), el archivo y las opciones; escribe `resultado.json` con los
archivos creados o el error. Códigos: 0, bien; 2, error de la herramienta (en el JSON); 5, sin memoria.
"""
import json
import sys


def main(job_path: str) -> int:
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    sys.path[:0] = job["paths"]
    from pathlib import Path

    from core.errors import ToolError
    from tools.mesh.pipeline import OP_TOOLS, convert_file, join_files, operate_file

    result_path = Path(job["result"])
    try:
        args = (job["options"], job["locale"], int(job["max_triangles"]), job["stem"], Path(job["out_dir"]))
        if job.get("srcs"):
            outputs = join_files([(Path(a), b, c) for a, b, c in job["srcs"]], *args)
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
