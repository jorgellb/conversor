"""ticket-a-excel (7.6 y 6.3): tickets de compra a Excel (XLSX) o CSV, una petición de IA por ticket.

1. En `workerocr`, Tesseract lee cada ticket (en escala de grises, con más contraste y ampliado si es pequeño) y el
   texto se guarda en `document_texts` del propietario; el trabajo pasa a `workerai`.
2. En `workerai` se reservan antes de empezar las peticiones de los tickets que no estén en la caché del propietario y
   se pide a cada uno un JSON con esquema (6.5): comercio, NIF, fecha, hora, conceptos, IVA por tipo, total, forma de
   pago y moneda. Se comprueba que los conceptos sumen el total (y la base más el IVA) y se avisa si no cuadra (D-163).
3. El XLSX tiene dos hojas (una fila por ticket y una por concepto); el CSV, la que se elija.
"""
from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

from core.ai.catalog import Needs
from core.ai.client import cached, remember
from core.ai.store import cache_key
from core.ai.text import estimate_tokens
from core.errors import ErrorCode, ToolError
from tools.ai import comun, hojas, imagen_texto
from tools.ai.documento import OCR_LANGS
from tools.base import InputFile, ToolContext, derived_name

TOOL = "ticket-a-excel"
MAX_TEXT = 12000
TOLERANCE = 0.011  # céntimos de redondeo
OUT_TOKENS = 1500
TEXTS = {
    "es": {
        "tickets": "Tickets", "lines": "Conceptos", "file": "Archivo", "shop": "Comercio", "nif": "NIF", "date": "Fecha",
        "time": "Hora", "count": "Conceptos", "sum": "Suma de conceptos", "total": "Total", "currency": "Moneda",
        "pay": "Forma de pago", "base": "Base {r} %", "tax": "IVA {r} %", "ok": "Cuadra", "concept": "Concepto",
        "qty": "Cantidad", "amount": "Importe", "yes": "Sí", "no": "No", "name": "tickets", "ocr": "Leyendo los tickets con OCR…",
        "mismatch": "No cuadran (revisa el ticket): {names}.", "skipped": "No parecen tickets y no se han incluido: {names}.",
    },
    "en": {
        "tickets": "Receipts", "lines": "Items", "file": "File", "shop": "Shop", "nif": "Tax ID", "date": "Date",
        "time": "Time", "count": "Items", "sum": "Sum of items", "total": "Total", "currency": "Currency",
        "pay": "Payment method", "base": "Net {r} %", "tax": "Tax {r} %", "ok": "Adds up", "concept": "Item",
        "qty": "Quantity", "amount": "Amount", "yes": "Yes", "no": "No", "name": "receipts", "ocr": "Reading the receipts with OCR…",
        "mismatch": "These do not add up (check the receipt): {names}.", "skipped": "These do not look like receipts and were left out: {names}.",
    },
}
NUM = {"type": ["number", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "es_ticket": {"type": "boolean"},
        "comercio": {"type": "string"}, "nif": {"type": "string"}, "fecha": {"type": "string"}, "hora": {"type": "string"},
        "moneda": {"type": "string"}, "forma_pago": {"type": "string"},
        "lineas": {"type": "array", "items": {"type": "object", "properties": {
            "concepto": {"type": "string"}, "cantidad": NUM, "importe": NUM},
            "required": ["concepto", "cantidad", "importe"], "additionalProperties": False}},
        "impuestos": {"type": "array", "items": {"type": "object", "properties": {
            "tipo": NUM, "base": NUM, "cuota": NUM}, "required": ["tipo", "base", "cuota"], "additionalProperties": False}},
        "total": NUM,
    },
    "required": ["es_ticket", "comercio", "nif", "fecha", "hora", "moneda", "forma_pago", "lineas", "impuestos", "total"],
    "additionalProperties": False,
}
SYSTEM = ("Extraes los datos de un ticket de compra o factura simplificada a partir del texto que ha leído un OCR. "
          f"{comun.GUARD} `es_ticket`: false si el texto no es un ticket ni una factura. Copia el nombre del comercio y su "
          "NIF o número de IVA tal cual; `fecha` en formato AAAA-MM-DD y `hora` en HH:MM (cadenas vacías si no aparecen); "
          "`moneda` con su código ISO 4217 (EUR si los importes van con € o no se indica en un ticket español). En "
          "`lineas`, cada concepto comprado con su cantidad y su importe total de la línea (impuestos incluidos, como en "
          "el ticket); en `impuestos`, cada tipo de IVA con su porcentaje, su base y su cuota. `total`: el importe final "
          "pagado. Los importes como números con punto decimal; null si no se leen. No inventes conceptos ni importes.")


def _texts(ctx: ToolContext) -> dict[str, str]:
    return TEXTS.get(ctx.locale, TEXTS["es"])


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return round(float(value), 2)


def _text(value, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def _date(value: str) -> str:
    value = _text(value, 20)
    for pattern, order in ((r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"), (r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", "dmy")):
        if m := re.match(pattern, value):
            parts = dict(zip(order, (int(g) for g in m.groups())))
            try:
                return date(parts["y"], parts["m"], parts["d"]).isoformat()
            except ValueError:
                return ""
    return ""


def clean(data) -> dict:
    """Ticket normalizado. Si el JSON no tiene la forma pedida o la mitad de los conceptos no sirven, se repara (6.5)."""
    if not isinstance(data, dict) or not isinstance(data.get("es_ticket"), bool):
        raise ValueError("falta «es_ticket»")
    if not data["es_ticket"]:
        return {"es_ticket": False}
    raw_lines = data.get("lineas") if isinstance(data.get("lineas"), list) else []
    lines = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        concept, amount = _text(item.get("concepto")), _number(item.get("importe"))
        if concept and amount is not None:
            lines.append({"concepto": concept, "cantidad": _number(item.get("cantidad")), "importe": amount})
    if raw_lines and len(lines) * 2 < len(raw_lines):
        raise ValueError("demasiados conceptos no válidos")
    taxes = []
    for item in data.get("impuestos") if isinstance(data.get("impuestos"), list) else []:
        if isinstance(item, dict) and (rate := _number(item.get("tipo"))) is not None and 0 <= rate <= 100:
            taxes.append({"tipo": rate, "base": _number(item.get("base")), "cuota": _number(item.get("cuota"))})
    total = _number(data.get("total"))
    if not lines and total is None:
        raise ValueError("ticket sin conceptos ni total")
    hour = _text(data.get("hora"), 8)
    currency = _text(data.get("moneda"), 3).upper()
    return {"es_ticket": True, "comercio": _text(data.get("comercio")), "nif": _text(data.get("nif"), 30),
            "fecha": _date(data.get("fecha", "")), "hora": hour if re.match(r"^\d{1,2}:\d{2}$", hour) else "",
            "moneda": currency if re.match(r"^[A-Z]{3}$", currency) else "", "forma_pago": _text(data.get("forma_pago"), 60),
            "lineas": lines, "impuestos": taxes, "total": total}


def adds_up(ticket: dict) -> bool | None:
    """Si los conceptos suman el total (y, si hay desglose, la base más el IVA también). None si no se puede saber."""
    total = ticket.get("total")
    if total is None or not ticket.get("lineas"):
        return None
    ok = abs(round(sum(line["importe"] for line in ticket["lineas"]), 2) - total) <= TOLERANCE
    parts = [(t["base"], t["cuota"]) for t in ticket.get("impuestos", [])]
    if parts and all(b is not None and c is not None for b, c in parts):
        ok = ok and abs(round(sum(b + c for b, c in parts), 2) - total) <= TOLERANCE * len(parts)
    return ok


def _preprocess(ctx: ToolContext, src: Path, n: int, k: int) -> Path:
    """Escala de grises, contraste y, en tickets pequeños, el doble de tamaño: Tesseract lee mejor la letra térmica."""
    from PIL import Image, ImageFilter, ImageOps

    with Image.open(src) as img:
        gray = ImageOps.autocontrast(img.convert("L").filter(ImageFilter.MedianFilter(3)))
    if gray.width < 1000 and gray.width * gray.height * 4 <= ctx.settings.IMAGE_MAX_PIXELS:
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
    dst = ctx.work / f"ticket-{n}-{k}.png"
    gray.save(dst)
    return dst


def languages(ctx: ToolContext) -> list[str]:
    return OCR_LANGS.get(ctx.options.idioma_ticket, ["spa", "eng"])


def _ocr_stage(ctx: ToolContext) -> list[dict]:
    from tools.ocr.imagen import check_languages, frames, straighten, tesseract_text

    langs = check_languages(ctx, languages(ctx))
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        if imagen_texto.load(ctx, inp, TOOL, langs) is not None:
            continue
        pages = [straighten(ctx, page, rotate=False, deskew=True) for page in frames(ctx, inp, n, max_frames=5)]
        text = "\n".join(tesseract_text(ctx, _preprocess(ctx, p, n, k), langs) for k, (p, _) in enumerate(pages))
        imagen_texto.save(ctx, inp, TOOL, langs, re.sub(r"\n{3,}", "\n\n", text).strip())
    ctx.handoff("ai", "ai", _texts(ctx)["ocr"])
    return []  # handoff lanza siempre


def _key(ctx: ToolContext, inp: InputFile) -> str:
    return cache_key(ctx.owner[0], ctx.owner[1], TOOL, inp.sha256, {"idioma": ctx.options.idioma_ticket}, ctx.locale)


def _extract(ctx: ToolContext, text: str) -> dict:
    body = text[:MAX_TEXT]
    data, _ = ctx.ai.complete_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Texto del ticket:\n<<<\n{body}\n>>>"}],
        needs=Needs(context=estimate_tokens(body) + OUT_TOKENS + 900, output=1000), max_tokens=OUT_TOKENS, schema=SCHEMA,
        check=clean)
    return {**data, "model": (ctx.ai.models_used or [""])[-1]}


def _rows(tickets: list[tuple[str, dict]], t: dict) -> tuple[list[list], list[list], set[int]]:
    rates = sorted({tax["tipo"] for _, tk in tickets for tax in tk["impuestos"]}, reverse=True)
    label = lambda r: f"{r:g}".replace(".", ",") if t is TEXTS["es"] else f"{r:g}"  # noqa: E731
    head = [t["file"], t["shop"], t["nif"], t["date"], t["time"], t["count"], t["sum"], t["total"], t["currency"], t["pay"]]
    for r in rates:
        head += [t["base"].format(r=label(r)), t["tax"].format(r=label(r))]
    head.append(t["ok"])
    money = {6, 7, *range(10, 10 + 2 * len(rates))}
    summary, lines = [head], [[t["file"], t["shop"], t["date"], t["concept"], t["qty"], t["amount"]]]
    for name, tk in tickets:
        when = date.fromisoformat(tk["fecha"]) if tk["fecha"] else None
        total_lines = round(sum(line["importe"] for line in tk["lineas"]), 2) if tk["lineas"] else None
        row = [name, tk["comercio"], tk["nif"], when, tk["hora"], len(tk["lineas"]), total_lines, tk["total"], tk["moneda"],
               tk["forma_pago"]]
        by_rate = {tax["tipo"]: tax for tax in tk["impuestos"]}
        for r in rates:
            row += [by_rate[r]["base"], by_rate[r]["cuota"]] if r in by_rate else [None, None]
        ok = adds_up(tk)
        row.append("" if ok is None else (t["yes"] if ok else t["no"]))
        summary.append(row)
        for line in tk["lineas"]:
            qty = line["cantidad"]
            qty = int(qty) if qty is not None and float(qty).is_integer() else qty
            lines.append([name, tk["comercio"], when, line["concepto"], qty, line["importe"]])
    return summary, lines, money


def _ai_stage(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    t = _texts(ctx)
    langs = languages(ctx)
    owner_type, owner_id = ctx.owner
    texts: list[tuple[InputFile, str, dict | None]] = []
    for inp in ctx.inputs:
        text = imagen_texto.load(ctx, inp, TOOL, langs)
        if text is None:
            raise ToolError(ErrorCode.INTERNAL, "texto del ticket no encontrado")
        known = cached(_key(ctx, inp), owner_type, owner_id) if imagen_texto.meaningful(text) else {"es_ticket": False}
        texts.append((inp, text, known))
    # 6.3: todas las peticiones reservadas antes de gastar la primera (las de la caché no cuentan).
    ctx.ai.budget.ensure(sum(1 for _, _, hit in texts if hit is None))
    tickets: list[tuple[str, dict]] = []
    skipped, models = [], []
    for n, (inp, text, hit) in enumerate(texts):
        ctx.report(0.1 + 0.8 * n / len(texts), None)
        data = hit
        if data is None:
            data = _extract(ctx, text)
            remember(_key(ctx, inp), owner_type, owner_id, data, ctx.expires_at)
        if not data.get("es_ticket"):
            skipped.append(inp.name)
            continue
        models.append(data.get("model") or "")
        tickets.append((inp.name, data))
    if not tickets:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "not_receipt")
    summary, lines, money = _rows(tickets, t)
    if len(ctx.inputs) == 1:
        name = derived_name(ctx.inputs[0].name, "", o.formato)
    else:
        name = f"{t['name']}.{o.formato}"
    dst = ctx.output(name)
    if o.formato == "xlsx":
        hojas.write_xlsx(dst, [hojas.Sheet(t["tickets"], summary, money=money),
                               hojas.Sheet(t["lines"], lines, money={5})], ctx.locale, numbers=False)
    else:
        dst.write_bytes(hojas.csv_bytes(summary if o.filas == "ticket" else lines, o.delimitador, ctx.locale))
    wrong = [nm for nm, tk in tickets if adds_up(tk) is False]
    parts = [comun.note(ctx, ctx.ai.budget.used == 0),
             comun.texts(ctx)["made"].format(model=next((m for m in reversed(models) if m), "") or "IA")]
    if wrong:
        parts.append(t["mismatch"].format(names=", ".join(wrong)))
    if skipped:
        parts.append(t["skipped"].format(names=", ".join(skipped)))
    return [{"path": str(dst), "name": name, "note": " ".join(parts)}]


def run(ctx: ToolContext) -> list[dict]:
    return _ai_stage(ctx) if ctx.stage == "ai" else _ocr_stage(ctx)
