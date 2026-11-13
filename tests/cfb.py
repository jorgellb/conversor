"""Escritor mínimo de archivos compuestos OLE2 (CFB v3) para crear mensajes MSG de prueba.

Solo lo justo para las pruebas: sectores de 512 bytes, sin mini stream (los flujos se rellenan hasta 4096 bytes con
ceros, que el lector de MSG ignora) y hermanos encadenados por la derecha en orden CFB.
"""
from __future__ import annotations

import struct

SECTOR = 512
FREE, END, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
MIN_STREAM = 4096


def _cfb_key(name: str) -> tuple[int, str]:
    return (len(name), name.upper())


def build(tree: dict) -> bytes:
    """`tree`: {nombre: bytes (flujo) | dict (almacenamiento)}. Devuelve el archivo CFB."""
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "children": [], "data": b""}]

    def add(node: dict, parent: int) -> None:
        for name in sorted(node, key=_cfb_key):
            value = node[name]
            index = len(entries)
            if isinstance(value, dict):
                entries.append({"name": name, "type": 1, "children": [], "data": b""})
                entries[parent]["children"].append(index)
                add(value, index)
            else:
                data = bytes(value)
                if len(data) < MIN_STREAM:
                    data += b"\x00" * (MIN_STREAM - len(data))
                entries.append({"name": name, "type": 2, "children": [], "data": data})
                entries[parent]["children"].append(index)

    add(tree, 0)
    # Sectores de datos de cada flujo, después el directorio y al final la FAT.
    sectors: list[bytes] = []
    fat: list[int] = []
    for e in entries:
        if e["type"] != 2:
            e["start"] = END
            continue
        e["start"] = len(sectors)
        chunks = [e["data"][i:i + SECTOR].ljust(SECTOR, b"\x00") for i in range(0, len(e["data"]), SECTOR)]
        for k, chunk in enumerate(chunks):
            sectors.append(chunk)
            fat.append(len(sectors) if k < len(chunks) - 1 else END)
    directory = b""
    for e in entries:
        children = e["children"]
        for a, b in zip(children, children[1:]):
            entries[a]["right"] = b
        e.setdefault("right", FREE)
    for e in entries:
        name = e["name"].encode("utf-16-le") + b"\x00\x00"
        child = e["children"][0] if e["children"] else FREE
        directory += struct.pack("<64sHBBIII16sIQQIQ", name.ljust(64, b"\x00"), len(name), e["type"], 1, FREE, e["right"], child,
                                 b"\x00" * 16, 0, 0, 0, e["start"], len(e["data"]))
    directory = directory.ljust(-(-len(directory) // SECTOR) * SECTOR, b"\x00")
    dir_start = len(sectors)
    dir_sectors = len(directory) // SECTOR
    for k in range(dir_sectors):
        sectors.append(directory[k * SECTOR:(k + 1) * SECTOR])
        fat.append(len(sectors) if k < dir_sectors - 1 else END)
    # Sectores FAT: cada uno guarda 128 entradas y se marca a sí mismo como FATSECT.
    n_fat = 1
    while (len(sectors) + n_fat) > n_fat * 128:
        n_fat += 1
    fat_start = len(sectors)
    fat += [FATSECT] * n_fat
    fat += [FREE] * (n_fat * 128 - len(fat))
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    for k in range(n_fat):
        sectors.append(fat_bytes[k * SECTOR:(k + 1) * SECTOR])
    difat = [fat_start + k for k in range(n_fat)] + [FREE] * (109 - n_fat)
    header = struct.pack("<8s16sHHHHH6sIIIIIIIII", bytes.fromhex("D0CF11E0A1B11AE1"), b"\x00" * 16, 0x3E, 3, 0xFFFE, 9, 6,
                         b"\x00" * 6, 0, n_fat, dir_start, 0, MIN_STREAM, END, 0, END, 0)
    header += struct.pack("<109I", *difat)
    return header + b"".join(sectors)


def utf16(text: str) -> bytes:
    return text.encode("utf-16-le")
