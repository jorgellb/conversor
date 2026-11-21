"""Landlock para los motores que leen rutas que escribe el usuario (12.3, F6-K, D-227): LaTeX con `\\input{/etc/hostname}`.

Landlock es el aislamiento sin privilegios del núcleo de Linux (5.13 o posterior): el proceso, antes del `exec`, se queda
con acceso solo a las rutas que se le dan; con el ABI 4 (Linux 6.7) tampoco puede abrir conexiones TCP. Se aplica en el
hijo de `run_engine` (después de `setsid` y de los límites) y no se puede quitar después. Si el núcleo o el perfil de
seccomp no lo permiten, el motor no arranca: nunca se ejecuta sin el aislamiento que pide la herramienta.
"""
from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path

SYS = {"x86_64": (444, 445, 446), "aarch64": (444, 445, 446)}
PR_SET_NO_NEW_PRIVS = 38
RULE_PATH_BENEATH = 1
CREATE_RULESET_VERSION = 1

EXECUTE, WRITE_FILE, READ_FILE, READ_DIR = 1 << 0, 1 << 1, 1 << 2, 1 << 3
REMOVE_DIR, REMOVE_FILE, MAKE_CHAR, MAKE_DIR, MAKE_REG = 1 << 4, 1 << 5, 1 << 6, 1 << 7, 1 << 8
MAKE_SOCK, MAKE_FIFO, MAKE_BLOCK, MAKE_SYM = 1 << 9, 1 << 10, 1 << 11, 1 << 12
REFER, TRUNCATE = 1 << 13, 1 << 14
FILE_RIGHTS = EXECUTE | WRITE_FILE | READ_FILE | TRUNCATE
NET_BIND_TCP, NET_CONNECT_TCP = 1 << 0, 1 << 1

MODES = {
    "r": READ_FILE | READ_DIR,
    "rx": READ_FILE | READ_DIR | EXECUTE,
    # Sin enlaces simbólicos (D-256): un motor comprometido podría dejar en su salida un enlace a un archivo de fuera que
    # el trabajador entregaría. «rws» solo para motores que los necesitan (Calibre, que no se puede probar aquí).
    "rw": READ_FILE | READ_DIR | WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_DIR | MAKE_REG | REFER | TRUNCATE,
    "rws": READ_FILE | READ_DIR | WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_DIR | MAKE_REG | MAKE_SYM | REFER | TRUNCATE,
}


class SandboxUnavailable(RuntimeError):
    pass


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64)]


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _libc():
    return ctypes.CDLL(None, use_errno=True)


def abi() -> int:
    """La versión de Landlock que ofrece el núcleo (0 si no hay)."""
    numbers = SYS.get(platform.machine())
    if numbers is None:
        return 0
    libc = _libc()
    libc.syscall.restype = ctypes.c_long
    version = libc.syscall(numbers[0], None, ctypes.c_size_t(0), ctypes.c_uint32(CREATE_RULESET_VERSION))
    return max(0, int(version))


def prepare(paths: list[tuple[Path, str]]):
    """Prepara en el padre el conjunto de reglas y devuelve la función que lo aplica en el hijo tras el fork.

    En el hijo solo quedan llamadas al sistema (`prctl` y `landlock_restrict_self`): nada de importar módulos ni
    cargar bibliotecas, que no es seguro después de un fork en un proceso con hilos. Los descriptores de las rutas y del
    conjunto se cierran en el hijo al hacer exec (O_CLOEXEC) y en el padre cuando se recoge la función.
    """
    numbers = SYS.get(platform.machine())
    version = abi()
    if numbers is None or version < 1:
        raise SandboxUnavailable("landlock")
    create, add, restrict_self = numbers
    libc = _libc()
    libc.syscall.restype = ctypes.c_long
    handled = (1 << 13) - 1
    if version >= 2:
        handled |= REFER
    if version >= 3:
        handled |= TRUNCATE
    attr = _RulesetAttr(handled, NET_BIND_TCP | NET_CONNECT_TCP if version >= 4 else 0)
    size = ctypes.sizeof(_RulesetAttr) if version >= 4 else 8
    ruleset = libc.syscall(create, ctypes.byref(attr), ctypes.c_size_t(size), ctypes.c_uint32(0))
    if ruleset < 0:
        raise SandboxUnavailable(f"landlock_create_ruleset {ctypes.get_errno()}")
    os.set_inheritable(ruleset, False)
    try:
        for path, mode in paths:
            if not path.exists():
                continue
            rights = MODES[mode] & handled
            if not path.is_dir():
                rights &= FILE_RIGHTS
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = _PathBeneath(rights, fd)
                if libc.syscall(add, ctypes.c_int(ruleset), ctypes.c_int(RULE_PATH_BENEATH), ctypes.byref(rule), ctypes.c_uint32(0)) < 0:
                    raise SandboxUnavailable(f"landlock_add_rule {ctypes.get_errno()}")
            finally:
                os.close(fd)
    except BaseException:
        os.close(ruleset)
        raise
    holder = _Ruleset(ruleset)
    prctl, syscall = libc.prctl, libc.syscall
    rs, no_new_privs = ctypes.c_int(ruleset), PR_SET_NO_NEW_PRIVS
    flags = ctypes.c_uint32(0)

    def apply() -> None:
        _ = holder  # mantiene abierto el conjunto mientras viva la función
        if prctl(no_new_privs, 1, 0, 0, 0) != 0:
            raise SandboxUnavailable("no_new_privs")
        if syscall(restrict_self, rs, flags) < 0:
            raise SandboxUnavailable("landlock_restrict_self")

    return apply


class _Ruleset:
    def __init__(self, fd: int) -> None:
        self.fd = fd

    def __del__(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def restrict(paths: list[tuple[Path, str]]) -> None:
    """Se queda (este proceso y sus hijos) con acceso solo a `paths` [(ruta, «r»|«rx»|«rw»)] y, con ABI 4, sin TCP."""
    prepare(paths)()
