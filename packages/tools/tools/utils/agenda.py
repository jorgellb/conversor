"""Contactos y calendarios (7.13, F6-I, D-224): vcf-a-csv, csv-a-vcf, vcf-a-excel, ics-a-csv, csv-a-ics e ics-a-excel.

- vCard con vobject (Apache-2.0): 2.1, 3.0 y 4.0 al leer; 3.0 al escribir, la que importan Google, Outlook, iCloud y los
  móviles. Las columnas siguen las plantillas de importación de Google Contacts y de Outlook (7.13), o una propia.
- iCalendar con icalendar (BSD-2-Clause): los eventos a una fila cada uno, con las plantillas de importación de Google
  Calendar y de Outlook o completa (con la zona horaria y la regla de repetición); al escribir, con su VTIMEZONE.
Categoría `data` con «vcf» o «ics» en el nombre: nunca crean cliente de IA (6.6 y 16.3). Las celdas que parecen una
fórmula llevan apóstrofo delante (12.3).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.pdf.common import with_batch_zip
from tools.utils.datos import MAX_DATA_BYTES, _write_csv, decode, guard_formula, read_csv, unguard

MAX_ITEMS = 100_000

NOTES = {
    "es": {"contacts": "{n} contacto(s).", "events": "{n} evento(s).", "photos": "{n} foto(s) de contacto no caben en una tabla y no se han incluido.",
           "recurring": "{n} evento(s) que se repiten salen una sola vez: las plantillas de Google y Outlook no admiten repeticiones (usa «Completa»).",
           "skipped_rows": "{n} fila(s) sin nombre ni datos de contacto se han saltado.", "bad_dates": "{n} fila(s) sin una fecha de inicio válida se han saltado.",
           "template": "Columnas reconocidas como plantilla de {name}.",
           "capped": "{n} dato(s) de contacto se han quitado: como mucho {max} correos, teléfonos, direcciones o webs por contacto.",
           "dropped": "{n} dato(s) (teléfonos, direcciones, correos o webs de más) no caben en la plantilla de Outlook: usa la de Google o la propia para conservarlos.",
           "bad_times": "{n} evento(s) con una hora que no se entiende han salido de día completo: revisa la columna de la hora."},
    "en": {"contacts": "{n} contact(s).", "events": "{n} event(s).", "photos": "{n} contact photo(s) do not fit in a table and were not included.",
           "recurring": "{n} recurring event(s) come out once: the Google and Outlook templates do not support recurrence (use “Full”).",
           "skipped_rows": "{n} row(s) without a name or contact details were skipped.", "bad_dates": "{n} row(s) without a valid start date were skipped.",
           "template": "Columns recognised as the {name} template.",
           "capped": "{n} contact detail(s) were removed: at most {max} emails, phones, addresses or websites per contact.",
           "dropped": "{n} detail(s) (extra phones, addresses, emails or websites) do not fit the Outlook template: use the Google or own template to keep them.",
           "bad_times": "{n} event(s) with a time that could not be understood came out as all-day: check the time column."},
}
TEMPLATE_NAMES = {"google": "Google", "outlook": "Outlook", "generico": "la herramienta"}


def _t(ctx: ToolContext) -> dict:
    return NOTES.get(ctx.locale, NOTES["es"])


# --- Contactos ----------------------------------------------------------------------------------------------------------


@dataclass
class Contact:
    given: str = ""
    family: str = ""
    middle: str = ""
    prefix: str = ""
    suffix: str = ""
    full: str = ""
    nickname: str = ""
    org: str = ""
    title: str = ""
    birthday: str = ""
    note: str = ""
    categories: list[str] = field(default_factory=list)
    emails: list[tuple[str, str]] = field(default_factory=list)  # (tipo, valor)
    phones: list[tuple[str, str]] = field(default_factory=list)
    addresses: list[tuple[str, dict]] = field(default_factory=list)  # (tipo, {street, city, region, code, country})
    urls: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.full or " ".join(p for p in (self.prefix, self.given, self.middle, self.family, self.suffix) if p) or self.org


KINDS = ("fax", "cell", "work", "home", "main", "other")  # el fax primero: «TYPE=WORK,FAX» es un fax
BARE_TYPES = {"cell", "mobile", "work", "home", "fax", "main", "pref", "voice", "internet", "pager", "car", "other", "msg",
              "x400", "dom", "intl", "postal", "parcel", "bbs", "modem", "isdn", "video"}
MAX_PER_KIND = 10  # correos, teléfonos, direcciones y webs por contacto: una tabla no crece sin límite (D-230)
MAX_CELLS = 5_000_000


def _kind(params: dict) -> str:
    types = {t.strip().lower() for v in params.get("TYPE", []) for t in str(v).split(",")}
    for t in KINDS:
        if t in types or (t == "cell" and "mobile" in types):
            return t
    return "other"


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), text)


def _split(text: str, sep: str) -> list[str]:
    """Parte por `sep` sin escapar (`\;` o `\,` no parten) y quita los escapes de cada trozo."""
    parts, cur, i = [], [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            cur.append(text[i:i + 2])
            i += 2
            continue
        if ch == sep:
            parts.append(_unescape("".join(cur)))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append(_unescape("".join(cur)))
    return parts


def _logical_lines(text: str) -> list[str]:
    """Desdobla las líneas (RFC 6350 3.2) y junta los saltos suaves de quoted-printable de vCard 2.1 («=» al final)."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    qp = False
    for line in raw:
        if out and qp and out[-1].endswith("="):
            out[-1] = out[-1][:-1] + line
        elif out and line[:1] in (" ", "\t"):
            out[-1] += line[1:]
        else:
            out.append(line)
        head = out[-1].split(":", 1)[0].upper()
        qp = "QUOTED-PRINTABLE" in head
    return [ln for ln in out if ln.strip()]


def _parse_line(line: str) -> tuple[str, dict[str, list[str]], str] | None:
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ":" and not in_quotes:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    pieces = head.split(";")
    name = pieces[0].split(".")[-1].strip().upper()  # «item1.TEL» (grupos de Apple)
    params: dict[str, list[str]] = {}
    for piece in pieces[1:]:
        if "=" in piece:
            key, val = piece.split("=", 1)
            params.setdefault(key.strip().upper(), []).extend(v.strip().strip('"') for v in val.split(","))
        elif piece.strip():
            # vCard 2.1: «TEL;CELL;WORK:…», parámetros sueltos que son tipos o la codificación.
            bare = piece.strip().lower()
            if bare in ("quoted-printable", "base64", "b", "8bit"):
                params.setdefault("ENCODING", []).append(bare.upper())
            elif bare in BARE_TYPES or bare.startswith("x-"):
                params.setdefault("TYPE", []).append(bare)
    return name, params, value


def _decode_value(value: str, params: dict[str, list[str]]) -> str:
    import quopri

    encoding = {e.upper() for e in params.get("ENCODING", [])}
    if "QUOTED-PRINTABLE" in encoding:
        charset = (params.get("CHARSET") or ["utf-8"])[0]
        data = quopri.decodestring(value.encode("latin-1", "replace"))
        try:
            return data.decode(charset)
        except (LookupError, UnicodeDecodeError):
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("cp1252", "replace")
    return value


def read_vcf(raw: bytes) -> tuple[list[Contact], int]:
    """vCard 2.1, 3.0 y 4.0 con un lector propio (D-230): vobject partía el texto en cada coma sin escapar (FN, TITLE,
    NOTE…), y vCard 2.1 no escapa las comas; también perdía los tipos sueltos de 2.1 y los saltos de quoted-printable."""
    text, _ = decode(raw)
    contacts, photos = [], 0
    c: Contact | None = None
    depth = 0
    for line in _logical_lines(text):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        key, params, value = parsed
        if key == "BEGIN" and value.strip().upper() == "VCARD":
            depth += 1
            if depth == 1:
                c = Contact()
            continue
        if key == "END" and value.strip().upper() == "VCARD":
            depth = max(0, depth - 1)
            if depth == 0 and c is not None:
                contacts.append(c)
                c = None
                if len(contacts) > MAX_ITEMS:
                    raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
            continue
        if c is None or depth != 1:
            continue  # fuera de una tarjeta o dentro de un AGENT anidado
        if key == "PHOTO":
            photos += 1
            continue
        value = _decode_value(value, params)
        kind = _kind(params)
        if key == "N":
            parts = (_split(value, ";") + [""] * 5)[:5]
            c.family, c.given, c.middle, c.prefix, c.suffix = (p.strip() for p in parts)
        elif key == "FN":
            c.full = _unescape(value).strip()
        elif key == "NICKNAME":
            c.nickname = _unescape(value).strip()
        elif key == "ORG":
            c.org = " ".join(p.strip() for p in _split(value, ";") if p.strip())
        elif key == "TITLE":
            c.title = _unescape(value).strip()
        elif key == "BDAY":
            c.birthday = _unescape(value).strip()
        elif key == "NOTE":
            c.note = _unescape(value).strip()
        elif key == "CATEGORIES":
            c.categories = [p.strip() for p in _split(value, ",") if p.strip()]
        elif key == "EMAIL" and value.strip():
            c.emails.append((kind, _unescape(value).strip()))
        elif key == "TEL" and value.strip():
            c.phones.append((kind, _unescape(value).strip().removeprefix("tel:")))
        elif key == "ADR":
            parts = (_split(value, ";") + [""] * 7)[:7]
            street = ", ".join(p.strip() for p in (parts[1], parts[2]) if p.strip())  # apartado y calle
            adr = {"street": street, "city": parts[3].strip(), "region": parts[4].strip(), "code": parts[5].strip(), "country": parts[6].strip()}
            if any(adr.values()):
                c.addresses.append((kind, adr))
        elif key == "URL" and value.strip():
            c.urls.append(_unescape(value).strip())
    if not contacts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    return contacts, photos


def cap_entries(contacts: list[Contact]) -> int:
    """Como mucho MAX_PER_KIND correos, teléfonos, direcciones y webs por contacto; devuelve cuántos se han quitado."""
    dropped = 0
    for c in contacts:
        for attr in ("emails", "phones", "addresses", "urls"):
            items = getattr(c, attr)
            if len(items) > MAX_PER_KIND:
                dropped += len(items) - MAX_PER_KIND
                setattr(c, attr, items[:MAX_PER_KIND])
    return dropped


def _s(value) -> str:
    if isinstance(value, list):
        return " ".join(_s(v) for v in value if v)
    return str(value).strip() if value is not None else ""


GOOGLE_LABEL = {"cell": "Mobile", "work": "Work", "home": "Home", "fax": "Work Fax", "main": "Main", "other": "Other"}
GOOGLE_TYPE = {v.lower(): k for k, v in GOOGLE_LABEL.items()} | {"mobile": "cell", "móvil": "cell", "trabajo": "work", "casa": "home"}


PHONE_COLUMNS = ("Business Phone", "Business Phone 2", "Home Phone", "Home Phone 2", "Mobile Phone", "Car Phone",
                 "Business Fax", "Home Fax", "Other Fax", "Pager", "Other Phone", "Primary Phone")
PHONE_SLOTS = {"work": ("Business Phone", "Business Phone 2"), "home": ("Home Phone", "Home Phone 2"), "cell": ("Mobile Phone", "Car Phone"),
               "fax": ("Business Fax", "Home Fax", "Other Fax"), "main": ("Primary Phone",), "other": ("Other Phone", "Primary Phone")}
OUTLOOK_PHONE_KIND = {"business phone": "work", "business phone 2": "work", "home phone": "home", "home phone 2": "home",
                      "mobile phone": "cell", "car phone": "cell", "business fax": "fax", "home fax": "fax", "other fax": "fax",
                      "primary phone": "main", "other phone": "other", "pager": "other"}


def contact_rows(contacts: list[Contact], template: str, locale: str, dropped: list[int] | None = None) -> list[list[str]]:
    """Filas de la tabla; `dropped[0]` suma los datos que no caben en la plantilla de Outlook."""
    dropped = dropped if dropped is not None else [0]
    if template == "google":
        n_mail = max((len(c.emails) for c in contacts), default=0) or 1
        n_tel = max((len(c.phones) for c in contacts), default=0) or 1
        n_adr = max((len(c.addresses) for c in contacts), default=0) or 1
        n_web = max((len(c.urls) for c in contacts), default=0) or 1
        header = ["First Name", "Middle Name", "Last Name", "Name Prefix", "Name Suffix", "Nickname", "Organization Name",
                  "Organization Title", "Birthday", "Notes", "Labels"]
        header += [f"E-mail {i} - {k}" for i in range(1, n_mail + 1) for k in ("Label", "Value")]
        header += [f"Phone {i} - {k}" for i in range(1, n_tel + 1) for k in ("Label", "Value")]
        header += [f"Address {i} - {k}" for i in range(1, n_adr + 1) for k in ("Label", "Street", "City", "Region", "Postal Code", "Country")]
        header += [f"Website {i} - {k}" for i in range(1, n_web + 1) for k in ("Label", "Value")]
        if len(header) * (len(contacts) + 1) > MAX_CELLS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
        rows = [header]
        for c in contacts:
            given = c.given or ("" if c.family else c.full)
            row = [given, c.middle, c.family, c.prefix, c.suffix, c.nickname, c.org, c.title, c.birthday, c.note,
                   " ::: ".join(c.categories + ["* myContacts"])]
            row += [x for i in range(n_mail) for x in ((GOOGLE_LABEL[c.emails[i][0]], c.emails[i][1]) if i < len(c.emails) else ("", ""))]
            row += [x for i in range(n_tel) for x in ((GOOGLE_LABEL[c.phones[i][0]], c.phones[i][1]) if i < len(c.phones) else ("", ""))]
            for i in range(n_adr):
                if i < len(c.addresses):
                    kind, a = c.addresses[i]
                    row += [GOOGLE_LABEL[kind], a["street"], a["city"], a["region"], a["code"], a["country"]]
                else:
                    row += [""] * 6
            row += [x for i in range(n_web) for x in (("Website", c.urls[i]) if i < len(c.urls) else ("", ""))]
            rows.append(row)
        return rows
    if template == "outlook":
        header = ["First Name", "Middle Name", "Last Name", "Title", "Suffix", "Nickname", "Company", "Job Title",
                  "E-mail Address", "E-mail 2 Address", "E-mail 3 Address", *PHONE_COLUMNS,
                  *(f"{p} {k}" for p in ("Home", "Business", "Other") for k in ("Street", "City", "State", "Postal Code", "Country/Region")),
                  "Web Page", "Birthday", "Notes", "Categories"]
        rows = [header]
        for c in contacts:
            phones = dict.fromkeys(PHONE_COLUMNS, "")
            for kind, value in c.phones:
                # Cada tipo a sus columnas y, si están llenas, a las de «otro»; lo que no cabe se cuenta en la nota.
                slot = next((col for col in PHONE_SLOTS.get(kind, ()) + PHONE_SLOTS["other"] if not phones[col]), None)
                if slot is None:
                    dropped[0] += 1
                else:
                    phones[slot] = value
            places: dict[str, dict | None] = {"home": None, "work": None, "other": None}
            for kind, a in c.addresses:
                slot = next((k for k in ((kind,) if kind in places else ()) + ("other", "home", "work") if places[k] is None), None)
                if slot is None:
                    dropped[0] += 1
                else:
                    places[slot] = a
            dropped[0] += max(0, len(c.emails) - 3) + max(0, len(c.urls) - 1)
            emails = [v for _, v in c.emails][:3] + [""] * 3
            def adr(a):
                return [a["street"], a["city"], a["region"], a["code"], a["country"]] if a else [""] * 5
            rows.append([c.given or ("" if c.family else c.full), c.middle, c.family, c.prefix, c.suffix, c.nickname, c.org, c.title,
                         *emails[:3], *phones.values(), *adr(places["home"]), *adr(places["work"]), *adr(places["other"]),
                         c.urls[0] if c.urls else "", c.birthday, c.note, ";".join(c.categories)])
        return rows
    es = locale == "es"
    header = (["Nombre completo", "Nombre", "Apellidos", "Empresa", "Cargo", "Correo electrónico", "Teléfono", "Dirección", "Web",
               "Cumpleaños", "Notas", "Grupos"] if es else
              ["Full name", "First name", "Last name", "Company", "Job title", "Email", "Phone", "Address", "Website", "Birthday",
               "Notes", "Groups"])
    rows = [header]
    for c in contacts:
        rows.append([c.name, c.given, c.family, c.org, c.title, "; ".join(v for _, v in c.emails), "; ".join(v for _, v in c.phones),
                     " | ".join(", ".join(x for x in (a["street"], a["code"], a["city"], a["region"], a["country"]) if x) for _, a in c.addresses),
                     "; ".join(c.urls), c.birthday, c.note, "; ".join(c.categories)])
    return rows


ALIASES = {
    "given": ("first name", "given name", "nombre", "nombre de pila"), "family": ("last name", "family name", "apellidos", "apellido"),
    "middle": ("middle name", "additional name", "segundo nombre"), "full": ("full name", "name", "nombre completo", "display name"),
    "prefix": ("name prefix", "title", "tratamiento"), "suffix": ("name suffix", "suffix"), "nickname": ("nickname", "apodo"),
    "org": ("organization name", "organization 1 - name", "company", "empresa", "organización"),
    "title": ("organization title", "organization 1 - title", "job title", "cargo", "puesto"),
    "birthday": ("birthday", "cumpleaños", "fecha de nacimiento"), "note": ("notes", "note", "notas"),
    "categories": ("labels", "group membership", "categories", "grupos", "etiquetas"),
}


def _template_of(header: list[str]) -> str:
    h = {x.strip().lower() for x in header}
    if any(x.startswith(("e-mail 1 - value", "phone 1 - value")) for x in h):
        return "google"
    if "e-mail address" in h or "mobile phone" in h or "business phone" in h:
        return "outlook"
    return "generico"


def contacts_from_csv(ctx: ToolContext, path: Path) -> tuple[list[Contact], str, int]:
    rows, _codec, _sep = read_csv(ctx, path, "auto")
    if not rows:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    header = [h.strip() for h in rows[0]]
    lower = [h.lower() for h in header]
    template = _template_of(header)
    contacts, skipped = [], 0
    for row in rows[1:]:
        cell = {lower[i]: unguard(v.strip()) for i, v in enumerate(row) if i < len(lower)}
        c = Contact()
        for attr, names in ALIASES.items():
            if template == "outlook" and attr == "prefix":
                names = ("title",)
            if template == "outlook" and attr == "title":
                names = ("job title",)
            value = next((cell[n] for n in names if cell.get(n)), "")
            if attr == "categories":
                c.categories = [x.strip() for x in re.split(r":::|;", value) if x.strip() and x.strip() != "* myContacts"]
            else:
                setattr(c, attr, value)
        for key, value in cell.items():
            if not value:
                continue
            m = re.fullmatch(r"(e-mail|phone|website) (\d+) - value", key)
            if m:
                label = cell.get(f"{m.group(1)} {m.group(2)} - label", "").lower().lstrip("* ")
                kind = GOOGLE_TYPE.get(label, "other")
                if m.group(1) == "e-mail":
                    c.emails += [(kind, v.strip()) for v in value.split(":::") if v.strip()]
                elif m.group(1) == "phone":
                    c.phones += [(kind, v.strip()) for v in value.split(":::") if v.strip()]
                else:
                    c.urls.append(value)
                continue
            m = re.fullmatch(r"address (\d+) - (street|formatted)", key)
            if m and (m.group(2) == "street" or not cell.get(f"address {m.group(1)} - street")):
                n = m.group(1)
                kind = GOOGLE_TYPE.get(cell.get(f"address {n} - label", "").lower(), "other")
                c.addresses.append((kind, {"street": value, "city": cell.get(f"address {n} - city", ""), "region": cell.get(f"address {n} - region", ""),
                                           "code": cell.get(f"address {n} - postal code", ""), "country": cell.get(f"address {n} - country", "")}))
                continue
            if key in ("e-mail address", "e-mail 2 address", "e-mail 3 address", "email", "e-mail", "correo", "correo electrónico", "correo electronico"):
                c.emails += [("other" if template != "outlook" else "work" if key == "e-mail address" else "other", v.strip()) for v in value.split(";") if v.strip()]
            elif key in OUTLOOK_PHONE_KIND or key in ("phone", "teléfono", "telefono", "móvil", "movil"):
                kind = OUTLOOK_PHONE_KIND.get(key) or {"móvil": "cell", "movil": "cell"}.get(key, "other")
                c.phones += [(kind, v.strip()) for v in value.split(";") if v.strip()]
            elif key in ("web page", "web", "website", "sitio web"):
                c.urls.append(value)
        for prefix_, kind in (("home", "home"), ("business", "work"), ("other", "other")):
            street = cell.get(f"{prefix_} street", "")
            if street or cell.get(f"{prefix_} city"):
                c.addresses.append((kind, {"street": street, "city": cell.get(f"{prefix_} city", ""), "region": cell.get(f"{prefix_} state", ""),
                                           "code": cell.get(f"{prefix_} postal code", ""), "country": cell.get(f"{prefix_} country/region", "")}))
        if template == "generico" and (cell.get("dirección") or cell.get("address")):
            value = cell.get("dirección") or cell.get("address")
            c.addresses += [("other", {"street": v.strip(), "city": "", "region": "", "code": "", "country": ""}) for v in value.split("|") if v.strip()]
        if not (c.name or c.emails or c.phones):
            skipped += 1
            continue
        contacts.append(c)
        if len(contacts) > MAX_ITEMS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
    return contacts, template, skipped


VCARD_TYPE = {"cell": "CELL", "work": "WORK", "home": "HOME", "fax": "FAX", "main": "MAIN", "other": "OTHER"}


def write_vcf(contacts: list[Contact]) -> bytes:
    import vobject

    out = []
    for c in contacts:
        card = vobject.vCard()
        card.add("n").value = vobject.vcard.Name(family=c.family, given=c.given, additional=c.middle, prefix=c.prefix, suffix=c.suffix)
        card.add("fn").value = c.name or (c.emails[0][1] if c.emails else c.phones[0][1] if c.phones else "?")
        for attr, key in (("nickname", "nickname"), ("title", "title"), ("birthday", "bday"), ("note", "note")):
            if getattr(c, attr):
                card.add(key).value = getattr(c, attr)
        if c.org:
            card.add("org").value = [c.org]
        if c.categories:
            card.add("categories").value = c.categories
        for kind, value in c.emails:
            line = card.add("email")
            line.value = value
            line.type_param = ["INTERNET", VCARD_TYPE.get(kind, "OTHER")] if kind != "other" else "INTERNET"
        for kind, value in c.phones:
            line = card.add("tel")
            line.value = value
            line.type_param = VCARD_TYPE.get(kind, "VOICE")
        for kind, a in c.addresses:
            line = card.add("adr")
            line.value = vobject.vcard.Address(street=a["street"], city=a["city"], region=a["region"], code=a["code"], country=a["country"])
            if kind != "other":
                line.type_param = VCARD_TYPE[kind]
        for url in c.urls:
            card.add("url").value = url
        out.append(card.serialize())
    return "".join(out).encode("utf-8")


# --- Calendarios -------------------------------------------------------------------------------------------------------


def calendar_zone(raw: bytes, choice: str):
    """La zona elegida o, con «calendario», la X-WR-TIMEZONE del archivo (la que pone Google al exportar) o Madrid."""
    if choice != "calendario":
        return ZoneInfo(choice)
    m = re.search(rb"^X-WR-TIMEZONE:([A-Za-z_/+-]{1,40})\s*$", raw[:200_000], re.M)
    try:
        return ZoneInfo(m.group(1).decode()) if m else ZoneInfo("Europe/Madrid")
    except (ValueError, KeyError, OSError):
        return ZoneInfo("Europe/Madrid")


def read_ics(raw: bytes) -> list:
    import icalendar

    text, _ = decode(raw)
    try:
        calendars = icalendar.Calendar.from_ical(text, multiple=True)
    except Exception as exc:  # noqa: BLE001 - icalendar lanza ValueError o IndexError con un archivo mal formado
        raise ToolError(ErrorCode.CORRUPT_FILE, "iCalendar no válido") from exc
    events = [ev for cal in calendars for ev in cal.walk("VEVENT")]
    if len(events) > MAX_ITEMS:
        raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
    if not events:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    return events


def _value(ev, key: str):
    prop = ev.get(key)
    return getattr(prop, "dt", prop) if prop is not None else None


def _text(ev, key: str) -> str:
    value = ev.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if hasattr(value, "cats"):
        return ", ".join(str(v) for v in value.cats)
    return str(value).strip()


def event_rows(events: list, template: str, locale: str, zone=None) -> tuple[list[list], int]:
    """`zone`: en las plantillas de Google y Outlook (que no llevan zona horaria) las horas se pasan a esa zona, la del
    calendario al que se importan; las horas «flotantes» (sin zona) se dejan como están (D-230)."""
    recurring = sum(1 for ev in events if ev.get("RRULE") is not None)
    if template in ("google", "outlook"):
        header = (["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location", "Private"]
                  if template == "google" else
                  ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All day event", "Description", "Location", "Categories", "Private"])
        rows = [header]
        for ev in events:
            start, end = _value(ev, "DTSTART"), _value(ev, "DTEND")
            if start is None:
                continue
            all_day = not isinstance(start, datetime)
            if end is None:
                end = start + (_value(ev, "DURATION") or (timedelta(days=1) if all_day else timedelta(0)))
            if all_day and isinstance(end, date):
                end = end - timedelta(days=1)  # en iCalendar el fin de un día completo es el día siguiente
            if zone is not None and not all_day:
                start, end = (v.astimezone(zone) if isinstance(v, datetime) and v.tzinfo else v for v in (start, end))
            def d(v):
                return v.strftime("%m/%d/%Y")
            def h(v):
                return v.strftime("%I:%M %p") if isinstance(v, datetime) else ""
            row = [_text(ev, "SUMMARY"), d(start), "" if all_day else h(start), d(end), "" if all_day else h(end),
                   "True" if all_day else "False", _text(ev, "DESCRIPTION"), _text(ev, "LOCATION")]
            if template == "outlook":
                row.append(_text(ev, "CATEGORIES"))
            row.append("True" if _text(ev, "CLASS").upper() in ("PRIVATE", "CONFIDENTIAL") else "False")
            rows.append(row)
        return rows, recurring
    es = locale == "es"
    header = (["Título", "Inicio", "Fin", "Todo el día", "Zona horaria", "Lugar", "Descripción", "Organizador", "Asistentes", "Estado",
               "Categorías", "Repetición", "UID"] if es else
              ["Title", "Start", "End", "All day", "Time zone", "Location", "Description", "Organizer", "Attendees", "Status",
               "Categories", "Recurrence", "UID"])
    rows = [header]
    for ev in events:
        start, end = _value(ev, "DTSTART"), _value(ev, "DTEND")
        if start is None:
            continue
        all_day = not isinstance(start, datetime)
        if end is None:
            end = start + (_value(ev, "DURATION") or (timedelta(days=1) if all_day else timedelta(0)))
        tz = str(start.tzinfo) if isinstance(start, datetime) and start.tzinfo else ""
        def iso(v):
            if isinstance(v, datetime):
                return v.replace(tzinfo=None).isoformat(sep=" ", timespec="minutes")
            return v.isoformat()
        attendees = ev.get("ATTENDEE")
        attendees = attendees if isinstance(attendees, list) else [attendees] if attendees else []
        rrule = ev.get("RRULE")
        rows.append([_text(ev, "SUMMARY"), iso(start), iso(end), ("sí" if es else "yes") if all_day else ("no"), tz,
                     _text(ev, "LOCATION"), _text(ev, "DESCRIPTION"), str(ev.get("ORGANIZER") or "").removeprefix("mailto:").removeprefix("MAILTO:"),
                     "; ".join(str(a).removeprefix("mailto:").removeprefix("MAILTO:") for a in attendees), _text(ev, "STATUS"),
                     _text(ev, "CATEGORIES"), rrule.to_ical().decode() if rrule is not None else "", _text(ev, "UID")])
    return rows, 0


EV_ALIASES = {
    "summary": ("subject", "summary", "title", "título", "titulo", "asunto", "evento", "nombre"),
    "start_date": ("start date", "fecha de inicio", "fecha inicio", "fecha", "date", "start", "inicio"),
    "start_time": ("start time", "hora de inicio", "hora inicio", "hora"),
    "end_date": ("end date", "fecha de fin", "fecha fin", "end", "fin"), "end_time": ("end time", "hora de fin", "hora fin"),
    "all_day": ("all day event", "all day", "todo el día", "todo el dia"),
    "location": ("location", "lugar", "ubicación", "ubicacion"), "description": ("description", "descripción", "descripcion", "notas"),
    "categories": ("categories", "categorías", "categorias"),
}


def _parse_date(text: str, order: str) -> tuple[date | None, time | None]:
    v = text.strip()
    if not v:
        return None, None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::\d{2})?)?", v)
    if m:
        try:
            d = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None, None
        return d, time(int(m[4]), int(m[5])) if m[4] else None
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?)?", v)
    if not m:
        return None, None
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    y += 2000 if y < 100 else 0
    day, month = (a, b) if order == "dia_mes" else (b, a)
    try:
        d = date(y, month, day)
    except ValueError:
        return None, None
    return d, (_time(f"{m[4]}:{m[5]} {m[6] or ''}") if m[4] else None)


def _time(text: str) -> time | None:
    """«9:30», «09:30:00», «9:30 PM», «9.30», «9:30 p. m.» y «9h30»."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.h](\d{2})(?::\d{2})?\s*([AaPp])?\.?\s*(?:[Mm]\.?)?\s*", text or "")
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2])
    if m[3]:
        hour = hour % 12 + (12 if m[3].lower() == "p" else 0)
    return time(hour, minute) if hour < 24 and minute < 60 else None


def events_from_csv(ctx: ToolContext, path: Path) -> tuple[bytes, int, int]:
    import icalendar

    o = ctx.options
    rows, _codec, _sep = read_csv(ctx, path, "auto")
    if not rows:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    lower = [h.strip().lower() for h in rows[0]]
    col = {k: next((lower.index(n) for n in names if n in lower), None) for k, names in EV_ALIASES.items()}
    if col["summary"] is None or col["start_date"] is None:
        raise ToolError(ErrorCode.INVALID_OPTIONS, "ics_no_columns")
    english = _template_of_events(lower)
    order = o.formato_fecha if o.formato_fecha != "auto" else ("mes_dia" if english else "dia_mes")
    tz = ZoneInfo(o.zona)
    cal = icalendar.Calendar()
    cal.add("prodid", "-//conversor//csv-a-ics//ES")
    cal.add("version", "2.0")
    added = bad = bad_times = 0
    for row in rows[1:]:
        def get(key):
            i = col[key]
            return row[i].strip() if i is not None and i < len(row) else ""

        start_d, start_t = _parse_date(get("start_date"), order)
        if start_d is None:
            bad += 1
            continue
        start_t = _time(get("start_time")) or start_t
        if get("start_time") and _time(get("start_time")) is None:
            bad_times += 1  # «9.30» o «9:00 a. m.»: sale de día completo, y se avisa
        end_d, end_t = _parse_date(get("end_date"), order)
        end_t = _time(get("end_time")) or end_t
        all_day = get("all_day").lower() in ("true", "sí", "si", "yes", "1", "verdadero") or start_t is None
        ev = icalendar.Event()
        ev.add("uid", f"{uuid.uuid4()}@conversor")
        ev.add("dtstamp", datetime.now(ZoneInfo("UTC")))
        ev.add("summary", get("summary") or "(sin título)")
        if all_day:
            ev.add("dtstart", start_d)
            ev.add("dtend", (end_d or start_d) + timedelta(days=1))
        else:
            start = datetime.combine(start_d, start_t, tz)
            end = datetime.combine(end_d or start_d, end_t, tz) if end_t else start + timedelta(hours=1)
            ev.add("dtstart", start)
            ev.add("dtend", end if end > start else start + timedelta(hours=1))
        for key, prop in (("location", "location"), ("description", "description")):
            if get(key):
                ev.add(prop, get(key))
        if get("categories"):
            ev.add("categories", [c.strip() for c in re.split(r"[;,]", get("categories")) if c.strip()])
        cal.add_component(ev)
        added += 1
        if added > MAX_ITEMS:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
    if not added:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    cal.add_missing_timezones()
    return cal.to_ical(), added, bad, bad_times


def _template_of_events(lower: list[str]) -> bool:
    return "start date" in lower or "subject" in lower


# --- Herramientas -----------------------------------------------------------------------------------------------------


def _xlsx(rows: list[list], dst: Path, title: str) -> None:
    import openpyxl
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title[:31])
    ws.freeze_panes = "A2"
    bold = Font(bold=True)
    for r, row in enumerate(rows):
        cells = []
        for value in row:
            cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", str(value))[:32_767] if value != "" else None)
            if value != "":
                cell.data_type = "s"  # nada se convierte en fórmula
            if r == 0:
                cell.font = bold
            cells.append(cell)
        ws.append(cells)
    wb.save(dst)


def run(ctx: ToolContext) -> list[dict]:
    t = _t(ctx)
    o = ctx.options
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        if inp.path.stat().st_size > MAX_DATA_BYTES:
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "Datos de más de 25 MB")
        notes: list[str] = []
        if ctx.tool in ("vcf-a-csv", "vcf-a-excel"):
            contacts, photos = read_vcf(inp.path.read_bytes())
            capped = cap_entries(contacts)
            dropped = [0]
            rows = contact_rows(contacts, o.plantilla, ctx.locale, dropped)
            notes.append(t["contacts"].format(n=len(contacts)))
            if photos:
                notes.append(t["photos"].format(n=photos))
            if capped:
                notes.append(t["capped"].format(n=capped, max=MAX_PER_KIND))
            if dropped[0]:
                notes.append(t["dropped"].format(n=dropped[0]))
        elif ctx.tool in ("ics-a-csv", "ics-a-excel"):
            raw = inp.path.read_bytes()
            events = read_ics(raw)
            zone = calendar_zone(raw, o.zona) if o.plantilla in ("google", "outlook") else None
            rows, recurring = event_rows(events, o.plantilla, ctx.locale, zone)
            notes.append(t["events"].format(n=len(rows) - 1))
            if recurring:
                notes.append(t["recurring"].format(n=recurring))
        elif ctx.tool == "csv-a-vcf":
            contacts, template, skipped = contacts_from_csv(ctx, inp.path)
            data = write_vcf(contacts)
            notes = [t["contacts"].format(n=len(contacts)), t["template"].format(name=TEMPLATE_NAMES[template])]
            if skipped:
                notes.append(t["skipped_rows"].format(n=skipped))
            name = derived_name(inp.name, "", "vcf")
            dst = ctx.output(name)
            dst.write_bytes(data)
            outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
            continue
        else:  # csv-a-ics
            data, added, bad, bad_times = events_from_csv(ctx, inp.path)
            notes = [t["events"].format(n=added)] + ([t["bad_dates"].format(n=bad)] if bad else [])
            notes += [t["bad_times"].format(n=bad_times)] if bad_times else []
            name = derived_name(inp.name, "", "ics")
            dst = ctx.output(name)
            dst.write_bytes(data)
            outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
            continue
        if ctx.tool.endswith("excel"):
            name = derived_name(inp.name, "", "xlsx")
            dst = ctx.output(name)
            _xlsx(rows, dst, Path(inp.name).stem or "datos")
        else:
            name = derived_name(inp.name, "", "csv")
            dst = ctx.output(name)
            guarded = ([guard_formula(str(v)) if v != "" else "" for v in row] for row in rows)
            notes += _write_csv(dst, guarded, ",", "utf-8-bom", ctx)
        outputs.append({"path": str(dst), "name": name, "note": " ".join(notes)})
    return with_batch_zip(ctx, outputs, f"{ctx.tool}.zip")

