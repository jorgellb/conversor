"""Restauración: `python -m app.ops.restore <archivo.dump>` (4.6)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from app.ops.backup import pg_args, pg_env
from core.settings import get_settings


def restore(database_url: str, dump_file: Path) -> None:
    url = make_url(database_url)
    subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", *pg_args(url), str(dump_file)],
                   env=pg_env(url), check=True, timeout=7200)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python -m app.ops.restore <archivo.dump>", file=sys.stderr)
        return 2
    restore(get_settings().DATABASE_URL, Path(argv[1]))
    print("Restauración terminada")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
