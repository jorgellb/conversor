"""F6-E (7.13, D-217): comprimidos con libarchive (16.4: ZIP con «../») y subtítulos con pysubs2."""
from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from test_media_tools import _rar4
from test_tools import make_ctx, run  # noqa: F401  (fixture)

libarchive = pytest.importorskip("libarchive")


def _write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(zf.namelist())


def _seven_zip(tmp_path: Path, files: dict[str, bytes]) -> Path:
    path = tmp_path / "copia.7z"
    with libarchive.file_writer(str(path), "7zip") as archive:
        for name, data in files.items():
            archive.add_file_from_memory(name, len(data), data)
    return path


def _tar(tmp_path: Path, name: str, mode: str, members: list[tarfile.TarInfo | tuple[str, bytes]]) -> Path:
    path = tmp_path / name
    with tarfile.open(path, mode) as tf:
        for m in members:
            if isinstance(m, tarfile.TarInfo):
                tf.addfile(m)
            else:
                info = tarfile.TarInfo(m[0])
                info.size, info.mtime = len(m[1]), 1_700_000_000
                tf.addfile(info, io.BytesIO(m[1]))
    return path


def test_rar_7z_and_tar_to_zip(make_ctx, tmp_path):
    rar = _write(tmp_path, "fotos.rar", _rar4({"a.txt": b"uno", "sub/b.txt": b"dos"}))
    out = run("rar-a-zip", make_ctx("rar-a-zip", [rar]))
    assert out[0]["name"] == "fotos.zip" and _names(Path(out[0]["path"])) == ["a.txt", "sub/b.txt"]
    assert out[0]["note"].startswith("2 archivo(s) en 1 carpeta(s)")
    seven = _seven_zip(tmp_path, {"datos/ñandú.csv": b"x,y\n", "léeme.txt": b"hola"})
    out = run("7z-a-zip", make_ctx("7z-a-zip", [seven]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["datos/ñandú.csv", "léeme.txt"] and zf.read("léeme.txt") == b"hola"
    for name, mode in (("copia.tar", "w"), ("copia.tar.gz", "w:gz"), ("copia.tgz", "w:gz"), ("copia.tar.bz2", "w:bz2"), ("copia.tar.xz", "w:xz")):
        src = _tar(tmp_path, name, mode, [("x/1.txt", b"1"), ("2.txt", b"22")])
        out = run("tar-a-zip", make_ctx("tar-a-zip", [src]))
        assert out[0]["name"] == "copia.zip", name
        with zipfile.ZipFile(out[0]["path"]) as zf:
            assert sorted(zf.namelist()) == ["2.txt", "x/1.txt"] and zf.getinfo("2.txt").date_time[0] == 2023


def test_traversal_links_and_devices_never_escape(make_ctx, tmp_path):
    """16.4: «../», rutas absolutas, letras de unidad y barras invertidas quedan dentro; enlaces y dispositivos, fuera."""
    link = tarfile.TarInfo("enlace")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    hard = tarfile.TarInfo("duro")
    hard.type, hard.linkname = tarfile.LNKTYPE, "../../etc/shadow"
    dev = tarfile.TarInfo("disp")
    dev.type = tarfile.CHRTYPE
    src = _tar(tmp_path, "malo.tar", "w", [("../../etc/cron.d/x", b"a"), ("/abs/y", b"b"), (r"C:\win\z.txt", b"c"), link, hard, dev])
    out = run("tar-a-zip", make_ctx("tar-a-zip", [src]))
    names = _names(Path(out[0]["path"]))
    assert all(not n.startswith(("/", "..")) and ".." not in n.split("/") and "\\" not in n for n in names)
    assert sorted(names) == ["abs/y", "etc/cron.d/x", "win/z.txt"]
    assert "3 enlace(s) o archivo(s) especiales" in out[0]["note"] and "3 ruta(s) peligrosas" in out[0]["note"]
    zipped = tmp_path / "salto.zip"
    with zipfile.ZipFile(zipped, "w") as zf:
        zf.writestr("../../fuera.txt", b"x")
    out = run("extraer-archivo-online", make_ctx("extraer-archivo-online", [zipped]))
    assert [o["name"] for o in out] == ["fuera.txt"] and not (tmp_path.parent / "fuera.txt").exists()


def test_extract_lists_files_and_zip(make_ctx, tmp_path):
    src = _write(tmp_path, "paquete.zip", b"")
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("a/informe.pdf", b"%PDF-1.4 uno")
        zf.writestr("b/informe.pdf", b"%PDF-1.4 dos")
        zf.writestr("notas.txt", b"hola")
    out = run("extraer-archivo-online", make_ctx("extraer-archivo-online", [src]))
    assert [o["name"] for o in out] == ["a_informe.pdf", "b_informe.pdf", "notas.txt", "paquete-extraido.zip"]
    assert Path(out[1]["path"]).read_bytes() == b"%PDF-1.4 dos" and out[0]["note"].startswith("3 archivo(s) en 2 carpeta(s)")
    many = _write(tmp_path, "muchos.zip", b"")
    with zipfile.ZipFile(many, "w") as zf:
        for i in range(60):
            zf.writestr(f"{i}.txt", b"x")
    out = run("extraer-archivo-online", make_ctx("extraer-archivo-online", [many]))
    assert [o["name"] for o in out] == ["muchos-extraido.zip"] and "más de 50 archivos" in out[0]["note"]


def test_encrypted_zip_needs_password(make_ctx, tmp_path):
    seven = tmp_path / "cifrado.zip"
    with libarchive.file_writer(str(seven), "zip", options="encryption=traditional", passphrase="clave") as archive:
        archive.add_file_from_memory("secreto.txt", 6, b"secret")
    with pytest.raises(ToolError) as err:
        run("extraer-archivo-online", make_ctx("extraer-archivo-online", [seven]))
    assert err.value.code == "PASSWORD_REQUIRED" and err.value.detail == "archive_password"
    with pytest.raises(ToolError) as err:
        run("extraer-archivo-online", make_ctx("extraer-archivo-online", [seven], secrets={"contrasena": "mala"}))
    assert err.value.code == "WRONG_PASSWORD"
    out = run("extraer-archivo-online", make_ctx("extraer-archivo-online", [seven], secrets={"contrasena": "clave"}))
    assert Path(out[0]["path"]).read_bytes() == b"secret"


def test_bomb_and_corrupt(make_ctx, tmp_path, monkeypatch):
    from tools.utils import comprimidos

    monkeypatch.setattr(comprimidos, "RATIO_FLOOR", 1000)
    bomb = _tar(tmp_path, "bomba.tar.gz", "w:gz", [("cero.bin", bytes(5_000_000))])
    with pytest.raises(ToolError) as err:
        run("tar-a-zip", make_ctx("tar-a-zip", [bomb]))
    assert err.value.code == "LIMIT_EXCEEDED"
    with pytest.raises(ToolError) as err:
        run("7z-a-zip", make_ctx("7z-a-zip", [_write(tmp_path, "roto.7z", b"7z\xbc\xaf\x27\x1c" + bytes(30))]))
    assert err.value.code == "CORRUPT_FILE"


# --- Subtítulos -------------------------------------------------------------------------------------------------------

SRT = ("1\r\n00:00:01,000 --> 00:00:02,500\r\nHola <i>mundo</i>\r\n\r\n"
       "2\r\n00:00:03,000 --> 00:00:04,000\r\n<b>Año</b> --> nuevo\r\nsegunda línea\r\n")
ASS = r"""[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1
Style: Cursiva,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,-1,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:03.00,0:00:04.00,Cursiva,,0,0,0,,en cursiva
Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Hola {\b1}mundo{\b0} & {\c&H0000FF&}rojo\Nsegunda
Comment: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,comentario
Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,{\p1}m 0 0 l 100 0 100 100{\p0}
Dialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,{\pos(10,10)\i1}cartel
"""


def test_srt_to_vtt_and_back(make_ctx, tmp_path):
    out = run("srt-a-vtt", make_ctx("srt-a-vtt", [_write(tmp_path, "peli.srt", SRT)]))
    vtt = Path(out[0]["path"]).read_text()
    assert out[0]["name"] == "peli.vtt" and vtt.startswith("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nHola <i>mundo</i>\n")
    assert "<b>Año</b> --&gt; nuevo\nsegunda línea" in vtt
    vtt_file = _write(tmp_path, "peli.vtt", vtt.replace("00:00:01.000 --> 00:00:02.500", "00:00:01.000 --> 00:00:02.500 align:start"))
    back = run("vtt-a-srt", make_ctx("vtt-a-srt", [vtt_file]))
    srt = Path(back[0]["path"]).read_bytes().decode()
    assert srt.startswith("1\r\n00:00:01,000 --> 00:00:02,500\r\nHola <i>mundo</i>\r\n") and "ajustes de posición" in back[0]["note"]
    plain = run("vtt-a-srt", make_ctx("vtt-a-srt", [vtt_file], {"etiquetas": "quitar"}))
    assert "<i>" not in Path(plain[0]["path"]).read_text()


def test_ass_to_srt_sorted_styles_and_no_drawings(make_ctx, tmp_path):
    out = run("ass-a-srt", make_ctx("ass-a-srt", [_write(tmp_path, "anime.ass", ASS)]))
    srt = Path(out[0]["path"]).read_bytes().decode().replace("\r\n", "\n")
    assert srt == ("1\n00:00:01,000 --> 00:00:02,500\nHola <b>mundo</b> & rojo\nsegunda\n\n"
                   "2\n00:00:01,500 --> 00:00:03,000\n<i>cartel</i>\n\n"
                   "3\n00:00:03,000 --> 00:00:04,000\n<i>en cursiva</i>\n")
    assert "2 comentario(s) o dibujo(s)" in out[0]["note"] and "3 subtítulos" in out[0]["note"]


def test_bad_subtitles(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("srt-a-vtt", make_ctx("srt-a-vtt", [_write(tmp_path, "vacio.srt", "esto no son subtítulos\n")]))
    assert err.value.code == "CORRUPT_FILE"
