"""heic-a-jpg y heic-a-png (A.10), raw-a-jpg (LibRaw con rawpy) y psd-a-png (psd-tools) en `workermedia` (7.11)."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name, open_image, run_engine, sanitize_filename, zip_files
from tools.media.imagenes import _heif_decoder, _natural
from tools.pdf.common import with_batch_zip

NOTES = {
    "es": {
        "no_exif": "{name}: no tenía datos EXIF.",
        "layers_skipped": "{name}: {n} capas no se han podido pintar (trazos vectoriales) y no van en el ZIP.",
        "no_layers": "{name}: no tiene capas de imagen; se entrega la imagen completa.",
        "merged": "{name}: el archivo no guarda la imagen combinada; se ha compuesto a partir de las capas.",
    },
    "en": {
        "no_exif": "{name}: it had no EXIF data.",
        "layers_skipped": "{name}: {n} layers could not be drawn (vector strokes) and are not in the ZIP.",
        "no_layers": "{name}: it has no image layers; the whole image is delivered.",
        "merged": "{name}: the file does not store the combined image; it was composed from the layers.",
    },
}


def _note(ctx: ToolContext, key: str, **kw) -> str:
    return NOTES.get(ctx.locale, NOTES["es"])[key].format(**kw)


def exif_for_output(raw: bytes | None, strip_gps: bool) -> bytes:
    """EXIF listo para el archivo nuevo: orientación 1 (los píxeles ya van girados) y, si se pide, sin el GPS."""
    if not raw:
        return b""
    from PIL import Image

    exif = Image.Exif()
    try:
        exif.load(raw)
    except Exception:  # noqa: BLE001 — EXIF ilegible: se descarta
        return b""
    if 0x0112 in exif:
        exif[0x0112] = 1
    if strip_gps:
        exif.pop(0x8825, None)
    return exif.tobytes()


def save_image(img, dst: Path, fmt: str, quality: int, exif: bytes, icc: bytes | None) -> None:
    """JPG (con fondo blanco si había transparencia) o PNG, con el EXIF y el perfil de color del original."""
    from PIL import Image

    kwargs: dict = {}
    if icc:
        kwargs["icc_profile"] = icc
    if exif:
        kwargs["exif"] = exif
    if fmt == "jpg":
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            img = flat
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dst, format="JPEG", quality=quality, optimize=True, **kwargs)
    else:
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        img.save(dst, format="PNG", optimize=False, compress_level=6, **kwargs)


# --- heic-a-jpg y heic-a-png ----------------------------------------------------------------------------------------


def _heif_exif(sidecar: Path) -> bytes | None:
    """El EXIF de HEIF empieza por 4 bytes con el desplazamiento hasta la cabecera TIFF."""
    if not sidecar.is_file():
        return None
    data = sidecar.read_bytes()
    if len(data) < 8:
        return None
    offset = int.from_bytes(data[:4], "big")
    tiff = data[4 + offset:]
    if tiff.startswith(b"Exif\x00\x00"):
        tiff = tiff[6:]
    return tiff if tiff[:4] in (b"II*\x00", b"MM\x00*") else None


def run_heic_image(ctx: ToolContext) -> list[dict]:
    """libheif solo para decodificar (D-49) a PNG sin pérdida; después, JPG o PNG con Pillow (A.10)."""
    o = ctx.options
    fmt = "jpg" if ctx.tool == "heic-a-jpg" else "png"
    decoder = _heif_decoder()
    outputs, notes = [], []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        out_dir = ctx.work / f"heic-{n}"
        out_dir.mkdir(parents=True, exist_ok=True)
        run_engine([decoder, "--with-exif", "--quiet", str(inp.path), str(out_dir / "foto.png")], cwd=out_dir, timeout=180, mem_mb=1536)
        produced = sorted(out_dir.glob("*.png"), key=lambda p: _natural(p.name))
        if not produced:
            raise ToolError(ErrorCode.CORRUPT_FILE, inp.name)
        for k, png in enumerate(produced):
            sidecar = png.with_suffix(".exif")
            raw = _heif_exif(sidecar if sidecar.exists() else out_dir / "foto.exif") if o.conservar_exif else None
            if o.conservar_exif and raw is None and k == 0:
                notes.append(_note(ctx, "no_exif", name=inp.name))
            suffix = "" if len(produced) == 1 else f"-{k + 1}"
            name = derived_name(inp.name, suffix, fmt)
            dst = ctx.output(name)
            with open_image(png, ctx.settings.IMAGE_MAX_PIXELS) as img:
                img.load()
                save_image(img, dst, fmt, o.calidad if fmt == "jpg" else 0, exif_for_output(raw, o.quitar_gps), img.info.get("icc_profile"))
            outputs.append({"path": str(dst), "name": name})
    if notes and outputs:
        outputs[0]["note"] = " ".join(notes)
    return with_batch_zip(ctx, outputs, f"fotos-{fmt}.zip")


# --- raw-a-jpg ------------------------------------------------------------------------------------------------------


# Etiquetas del IFD0 que se copian: fabricante, modelo, programa, fecha, autor y copyright.
RAW_IFD0_TAGS = (0x010F, 0x0110, 0x0131, 0x0132, 0x013B, 0x8298)


def raw_exif(path: Path) -> bytes | None:
    """EXIF de un RAW sobre TIFF (CR2, NEF, ARW y DNG) leído de sus IFD con Pillow, sin decodificar la imagen.

    Se copian el IFD0 básico, el subIFD EXIF (sin la MakerNote, cuyos desplazamientos dejarían de valer) y el GPS.
    """
    from PIL import Image, TiffImagePlugin

    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if head[:4] not in (b"II*\x00", b"MM\x00*"):
                return None
            ifd0 = TiffImagePlugin.ImageFileDirectory_v2(head)
            f.seek(ifd0.next)
            ifd0.load(f)

            def sub(tag: int) -> dict:
                offset = ifd0.get(tag)
                if not isinstance(offset, int) or offset <= 0:
                    return {}
                ifd = TiffImagePlugin.ImageFileDirectory_v2(head)
                f.seek(offset)
                ifd.load(f)
                return dict(ifd)

            exif = Image.Exif()
            for tag in RAW_IFD0_TAGS:
                if tag in ifd0:
                    exif[tag] = ifd0[tag]
            sub_exif = {k: v for k, v in sub(0x8769).items() if k != 0x927C}
            if sub_exif:
                exif[0x8769] = sub_exif
            gps = sub(0x8825)
            if gps:
                exif[0x8825] = gps
            return exif.tobytes() if len(exif) else None
    except Exception:  # noqa: BLE001 — sin EXIF legible
        return None


def run_raw(ctx: ToolContext) -> list[dict]:
    """LibRaw revela el RAW en un subproceso aislado (raw_runner.py); el JPG se escribe aquí con su EXIF."""
    o = ctx.options
    runner = Path(__file__).with_name("raw_runner.py")
    outputs, notes = [], []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        png = ctx.work / f"raw-{n}.png"
        args = json.dumps({"balance": o.balance_blancos, "brillo_automatico": o.brillo_automatico, "tamano": o.tamano,
                           "max_pixels": ctx.settings.IMAGE_MAX_PIXELS})
        res = run_engine([sys.executable, "-I", str(runner), str(inp.path), str(png), args], cwd=ctx.work, timeout=300, mem_mb=2048,
                         ok_codes=(0, 3, 4))
        if res.returncode == 3:
            raise ToolError(ErrorCode.CORRUPT_FILE, inp.name)
        if res.returncode == 4:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, inp.name)
        raw = raw_exif(inp.path) if o.conservar_exif else None
        if o.conservar_exif and raw is None:
            notes.append(_note(ctx, "no_exif", name=inp.name))
        name = derived_name(inp.name, "", "jpg")
        dst = ctx.output(name)
        with open_image(png, ctx.settings.IMAGE_MAX_PIXELS) as img:
            img.load()
            save_image(img, dst, "jpg", o.calidad, exif_for_output(raw, o.quitar_gps), None)
        outputs.append({"path": str(dst), "name": name})
    if notes and outputs:
        outputs[0]["note"] = " ".join(notes)
    return with_batch_zip(ctx, outputs, "fotos-jpg.zip")


# --- psd-a-png ------------------------------------------------------------------------------------------------------


def _layer_name(name: str, used: set[str]) -> str:
    base = sanitize_filename(re.sub(r"\s+", " ", name or "capa").strip())[:60] or "capa"
    candidate, k = base, 2
    while candidate.lower() in used:
        candidate, k = f"{base}-{k}", k + 1
    used.add(candidate.lower())
    return candidate


def run_psd(ctx: ToolContext) -> list[dict]:
    """La imagen combinada que guarda Photoshop (o compuesta por psd-tools si no está) o cada capa visible en PNG."""
    from PIL import Image
    from psd_tools import PSDImage

    o = ctx.options
    outputs, notes = [], []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        try:
            psd = PSDImage.open(inp.path)
        except Exception as exc:  # noqa: BLE001 — psd-tools no lo reconoce
            raise ToolError(ErrorCode.CORRUPT_FILE, inp.name) from exc
        if psd.width * psd.height > ctx.settings.IMAGE_MAX_PIXELS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, inp.name)
        if o.salida == "capas":
            files: list[tuple[Path, str]] = []
            used: set[str] = set()
            skipped = 0
            work = ctx.work / f"psd-{n}"
            work.mkdir(parents=True, exist_ok=True)
            for k, layer in enumerate(psd.descendants()):
                if layer.is_group() or not layer.is_visible() or layer.width == 0 or layer.height == 0:
                    continue
                try:
                    img = layer.composite()
                except ImportError:
                    skipped += 1
                    continue
                if img is None:
                    continue
                path = work / f"capa-{k:04d}.png"
                img.save(path, format="PNG")
                files.append((path, f"{_layer_name(layer.name, used)}.png"))
            if skipped:
                notes.append(_note(ctx, "layers_skipped", name=inp.name, n=skipped))
            if files:
                name = derived_name(inp.name, "-capas", "zip")
                dst = ctx.output(name)
                zip_files(files, dst)
                outputs.append({"path": str(dst), "name": name})
                continue
            notes.append(_note(ctx, "no_layers", name=inp.name))
        merged = psd.topil()
        if merged is None:
            notes.append(_note(ctx, "merged", name=inp.name))
            merged = psd.composite()
        if merged is None:
            raise ToolError(ErrorCode.CORRUPT_FILE, inp.name)
        if not o.transparencia and merged.mode in ("RGBA", "LA"):
            flat = Image.new("RGB", merged.size, (255, 255, 255))
            flat.paste(merged, mask=merged.getchannel("A"))
            merged = flat
        name = derived_name(inp.name, "", "png")
        dst = ctx.output(name)
        buf = io.BytesIO()
        merged.save(buf, format="PNG")
        dst.write_bytes(buf.getvalue())
        outputs.append({"path": str(dst), "name": name})
    if notes and outputs:
        outputs[0]["note"] = " ".join(notes)
    return with_batch_zip(ctx, outputs, "imagenes-png.zip")

