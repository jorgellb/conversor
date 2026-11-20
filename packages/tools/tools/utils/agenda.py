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
           "template": "Columnas reconocidas como plantilla de {name}."},
    "en": {"contacts": "{n} contact(s).", "events": "{n} event(s).", "photos": "{n} contact photo(s) do not fit in a table and were not included.",
           "recurring": "{n} recurring event(s) come out once: the Google and Outlook templates do not support recurrence (use “Full”).",
           "skipped_rows": "{n} row(s) without a name or contact details were skipped.", "bad_dates": "{n} row(s) without a valid start date were skipped.",
           "template": "Columns recognised as the {name} template."},
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


def _kind(params: dict) -> str:
    types = {str(v).lower() for v in params.get("TYPE", []) for v in str(v).split(",")}
    for t in ("cell", "work", "home", "fax", "main", "other"):
        if t in types or (t == "cell" and "mobile" in types):
            return t
    return "other"


def read_vcf(raw: bytes) -> tuple[list[Contact], int]:
    import vobject

    text, _ = decode(raw)
    contacts, photos = [], 0
    try:
        for card in vobject.readComponents(text, ignoreUnreadable=True):
            if card.name != "VCARD":
                continue
            c = Contact()
            for line in card.getChildren():
                key, value, params = line.name.upper(), line.value, line.params
                if key == "N" and hasattr(value, "given"):
                    c.given, c.family = _s(value.given), _s(value.family)
                    c.middle, c.prefix, c.suffix = _s(value.additional), _s(value.prefix), _s(value.suffix)
                elif key == "FN":
                    c.full = _s(value)
                elif key == "NICKNAME":
                    c.nickname = _s(value)
                elif key == "ORG":
                    c.org = " ".join(_s(v) for v in value) if isinstance(value, list) else _s(value)
                elif key == "TITLE":
                    c.title = _s(value)
                elif key == "BDAY":
                    c.birthday = _s(value)
                elif key == "NOTE":
                    c.note = _s(value)
                elif key == "CATEGORIES":
                    c.categories = [_s(v) for v in (value if isinstance(value, list) else [value]) if _s(v)]
                elif key == "EMAIL" and _s(value):
                    c.emails.append((_kind(params), _s(value)))
                elif key == "TEL" and _s(value):
                    c.phones.append((_kind(params), _s(value)))
                elif key == "ADR" and hasattr(value, "street"):
                    c.addresses.append((_kind(params), {"street": _s(value.street), "city": _s(value.city), "region": _s(value.region),
                                                        "code": _s(value.code), "country": _s(value.country)}))
                elif key == "URL" and _s(value):
                    c.urls.append(_s(value))
                elif key == "PHOTO":
                    photos += 1
            contacts.append(c)
            if len(contacts) > MAX_ITEMS:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "agenda_too_many")
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - vobject lanza ParseError, ValueError o KeyError con un vCard mal formado
        raise ToolError(ErrorCode.CORRUPT_FILE, "vCard no válido") from exc
    if not contacts:
        raise ToolError(ErrorCode.CORRUPT_FILE, "agenda_empty")
    return contacts, photos


def _s(value) -> str:
    if isinstance(value, list):
        return " ".join(_s(v) for v in value if v)
    return str(value).strip() if value is not None else ""


GOOGLE_LABEL = {"cell": "Mobile", "work": "Work", "home": "Home", "fax": "Work Fax", "main": "Main", "other": "Other"}
GOOGLE_TYPE = {v.lower(): k for k, v in GOOGLE_LABEL.items()} | {"mobile": "cell", "móvil": "cell", "trabajo": "work", "casa": "home"}


def contact_rows(contacts: list[Contact], template: str, locale: str) -> list[list[str]]:
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
                  "E-mail Address", "E-mail 2 Address", "E-mail 3 Address", "Business Phone", "Home Phone", "Mobile Phone",
                  "Business Fax", "Other Phone", "Home Street", "Home City", "Home State", "Home Postal Code", "Home Country/Region",
                  "Business Street", "Business City", "Business State", "Business Postal Code", "Business Country/Region",
                  "Web Page", "Birthday", "Notes", "Categories"]
        rows = [header]
        for c in contacts:
            phones = {"work": "", "home": "", "cell": "", "fax": "", "other": ""}
            for kind, value in c.phones:
                slot = kind if kind in phones else "other"
                phones[slot] = phones[slot] or value
            home = next((a for k, a in c.addresses if k == "home"), None) or (c.addresses[0][1] if c.addresses and c.addresses[0][0] != "work" else None)
            work = next((a for k, a in c.addresses if k == "work"), None)
            emails = [v for _, v in c.emails][:3] + [""] * 3
            def adr(a):
                return [a["street"], a["city"], a["region"], a["code"], a["country"]] if a else [""] * 5
            rows.append([c.given or ("" if c.family else c.full), c.middle, c.family, c.prefix, c.suffix, c.nickname, c.org, c.title,
                         *emails[:3], phones["work"], phones["home"], phones["cell"], phones["fax"], phones["other"],
                         *adr(home), *adr(work), c.urls[0] if c.urls else "", c.birthday, c.note, ";".join(c.categories)])
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
            elif key in ("business phone", "home phone", "mobile phone", "business fax", "other phone", "phone", "teléfono", "telefono", "móvil", "movil"):
                kind = {"business phone": "work", "home phone": "home", "mobile phone": "cell", "business fax": "fax", "móvil": "cell", "movil": "cell"}.get(key, "other")
                c.phones += [(kind, v.strip()) for v in value.split(";") if v.strip()]
            elif key in ("web page", "web", "website", "sitio web"):
                c.urls.append(value)
        for prefix_, kind in (("home", "home"), ("business", "work")):
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


def event_rows(events: list, template: str, locale: str) -> tuple[list[list], int]:
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
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?\s*", text or "")
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2])
    if m[3]:
        hour = hour % 12 + (12 if m[3].lower() == "pm" else 0)
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
    added = bad = 0
    for row in rows[1:]:
        def get(key):
            i = col[key]
            return row[i].strip() if i is not None and i < len(row) else ""

        start_d, start_t = _parse_date(get("start_date"), order)
        if start_d is None:
            bad += 1
            continue
        start_t = _time(get("start_time")) or start_t
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
    return cal.to_ical(), added, bad


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
            rows = contact_rows(contacts, o.plantilla, ctx.locale)
            notes.append(t["contacts"].format(n=len(contacts)))
            if photos:
                notes.append(t["photos"].format(n=photos))
        elif ctx.tool in ("ics-a-csv", "ics-a-excel"):
            events = read_ics(inp.path.read_bytes())
            rows, recurring = event_rows(events, o.plantilla, ctx.locale)
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
            data, added, bad = events_from_csv(ctx, inp.path)
            notes = [t["events"].format(n=added)] + ([t["bad_dates"].format(n=bad)] if bad else [])
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

