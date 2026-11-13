// Contenido de generar-codigo-qr (A.1): URL, WiFi, texto, vCard, SEPA (EPC), PayPal, correo, teléfono, SMS y evento.
// Sin dependencias: lo usa también la página (hilo principal) para la vista previa.
import { ToolError } from "./tool-error";

export type QrType = "url" | "wifi" | "texto" | "vcard" | "sepa" | "paypal" | "email" | "telefono" | "sms" | "evento";
export type QrMode = "byte" | "numerico" | "alfanumerico" | "kanji";

export interface QrContent {
  tipo: QrType;
  url?: string;
  wifi_ssid?: string;
  wifi_contrasena?: string;
  wifi_cifrado?: "WPA" | "WEP" | "nopass";
  wifi_oculta?: boolean;
  texto?: string;
  vcard_nombre?: string;
  vcard_apellidos?: string;
  vcard_nombre_visible?: string;
  vcard_email?: string;
  vcard_empresa?: string;
  vcard_cargo?: string;
  vcard_web?: string;
  vcard_telefono?: string;
  vcard_tipo_telefono?: "trabajo" | "movil" | "personal" | "otro";
  sepa_beneficiario?: string;
  sepa_iban?: string;
  sepa_bic?: string;
  sepa_importe?: number | null;
  sepa_concepto?: string;
  paypal_cuenta?: string;
  paypal_importe?: number | null;
  paypal_moneda?: string;
  email_para?: string;
  email_asunto?: string;
  email_mensaje?: string;
  telefono_numero?: string;
  sms_numero?: string;
  sms_mensaje?: string;
  evento_titulo?: string;
  evento_inicio?: string;
  evento_fin?: string;
  evento_todo_el_dia?: boolean;
  evento_lugar?: string;
  evento_descripcion?: string;
}

/** Error de un dato del QR: `key` es la clave del mensaje en la web (qr.err.<clave>) y `params`, sus valores. */
export class QrInputError extends ToolError {
  constructor(readonly key: string, readonly params: Record<string, string> = {}) {
    super("INVALID_OPTIONS", key);
  }
}

const invalid = (key: string, params: Record<string, string> = {}): never => {
  throw new QrInputError(key, params);
};

const clean = (v: string | undefined | null) => (v ?? "").trim();

// ——— Validaciones ———

/** Longitud del IBAN por país (registro SWIFT del IBAN). */
const IBAN_LENGTH: Record<string, number> = {
  AD: 24, AE: 23, AL: 28, AT: 20, AZ: 28, BA: 20, BE: 16, BG: 22, BH: 22, BI: 27, BR: 29, BY: 28, CH: 21, CR: 22, CY: 28,
  CZ: 24, DE: 22, DJ: 27, DK: 18, DO: 28, EE: 20, EG: 29, ES: 24, FI: 18, FK: 18, FO: 18, FR: 27, GB: 22, GE: 22, GI: 23,
  GL: 18, GR: 27, GT: 28, HR: 21, HU: 28, IE: 22, IL: 23, IQ: 23, IS: 26, IT: 27, JO: 30, KW: 30, KZ: 20, LB: 28, LC: 32,
  LI: 21, LT: 20, LU: 20, LV: 21, LY: 25, MC: 27, MD: 24, ME: 22, MK: 19, MN: 20, MR: 27, MT: 31, MU: 30, NI: 28, NL: 18,
  NO: 15, OM: 23, PK: 24, PL: 28, PS: 29, PT: 25, QA: 29, RO: 24, RS: 22, RU: 33, SA: 24, SC: 31, SD: 18, SE: 24, SI: 19,
  SK: 24, SM: 27, SO: 23, ST: 25, SV: 28, TL: 23, TN: 24, TR: 26, UA: 29, VA: 22, VG: 24, XK: 20, YE: 30,
};

/** IBAN sin espacios y en mayúsculas si es válido (país, longitud y dígitos de control mod 97); si no, null. */
export function normalizeIban(value: string): string | null {
  const iban = value.replace(/[\s-]/g, "").toUpperCase();
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/.test(iban)) return null;
  if (IBAN_LENGTH[iban.slice(0, 2)] !== iban.length) return null;
  const moved = iban.slice(4) + iban.slice(0, 4);
  let rest = 0;
  for (const ch of moved) {
    const n = ch >= "A" ? String(ch.charCodeAt(0) - 55) : ch;
    for (const d of n) rest = (rest * 10 + Number(d)) % 97;
  }
  return rest === 1 ? iban : null;
}

export function isBic(value: string): boolean {
  return /^[A-Z]{4}[A-Z]{2}[A-Z2-9][A-NP-Z0-9](?:[A-Z0-9]{3})?$/.test(value);
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function phone(value: string, what: "phone" | "vcard_phone" | "sms_phone"): string {
  const v = clean(value).replace(/[\s().-]/g, "");
  if (!/^\+?\d{3,20}$/.test(v)) invalid("phone_invalid", { field: what });
  return v;
}

function amount(value: number | null | undefined, max = 999_999_999.99): string | null {
  if (value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))) return null;
  const n = Number(value);
  if (!(n >= 0.01 && n <= max)) invalid("amount_range");
  if (Math.round(n * 100) !== n * 100 && Math.abs(Math.round(n * 100) - n * 100) > 1e-6) invalid("amount_decimals");
  return n.toFixed(2);
}

// ——— Escapes ———

const escWifi = (v: string) => v.replace(/([\\;,:"])/g, "\\$1");
const escVcard = (v: string) => v.replace(/\\/g, "\\\\").replace(/([,;])/g, "\\$1").replace(/\r?\n/g, "\\n");

/** «2026-11-04T10:30» (hora local de la persona) → «20261104T103000», sin zona horaria (hora flotante). */
function icalDate(value: string, allDay: boolean): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(clean(value));
  if (!m) invalid("date_invalid");
  const [, y, mo, d, h = "00", mi = "00"] = m!;
  return allDay ? `${y}${mo}${d}` : `${y}${mo}${d}T${h}${mi}00`;
}

function nextDay(yyyymmdd: string): string {
  const d = new Date(Date.UTC(Number(yyyymmdd.slice(0, 4)), Number(yyyymmdd.slice(4, 6)) - 1, Number(yyyymmdd.slice(6, 8)) + 1));
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}

const PHONE_TYPE = { trabajo: "WORK,VOICE", movil: "CELL", personal: "HOME,VOICE", otro: "VOICE" } as const;

/** Texto que se codifica en el QR según el tipo, con los formatos que leen las cámaras y las apps de banca. */
export function qrPayload(o: QrContent): string {
  switch (o.tipo) {
    case "url": {
      const url = clean(o.url);
      if (!url) invalid("url_missing");
      return /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `https://${url}`;
    }
    case "texto": {
      const text = o.texto ?? "";
      if (!text.trim()) invalid("text_missing");
      return text;
    }
    case "wifi": {
      const ssid = o.wifi_ssid ?? "";
      if (!ssid) invalid("ssid_missing");
      const type = o.wifi_cifrado ?? "WPA";
      const parts = [`T:${type}`, `S:${escWifi(ssid)}`];
      if (type !== "nopass") {
        if (!o.wifi_contrasena) invalid("wifi_password_missing");
        parts.push(`P:${escWifi(o.wifi_contrasena!)}`);
      }
      if (o.wifi_oculta) parts.push("H:true");
      return `WIFI:${parts.join(";")};;`;
    }
    case "vcard": {
      const first = clean(o.vcard_nombre);
      const last = clean(o.vcard_apellidos);
      const display = clean(o.vcard_nombre_visible) || [first, last].filter(Boolean).join(" ");
      if (!display) invalid("name_missing");
      const email = clean(o.vcard_email);
      if (email && !EMAIL.test(email)) invalid("email_invalid");
      const lines = ["BEGIN:VCARD", "VERSION:3.0", `N:${escVcard(last)};${escVcard(first)};;;`, `FN:${escVcard(display)}`];
      if (clean(o.vcard_empresa)) lines.push(`ORG:${escVcard(clean(o.vcard_empresa))}`);
      if (clean(o.vcard_cargo)) lines.push(`TITLE:${escVcard(clean(o.vcard_cargo))}`);
      if (clean(o.vcard_telefono)) lines.push(`TEL;TYPE=${PHONE_TYPE[o.vcard_tipo_telefono ?? "trabajo"]}:${phone(o.vcard_telefono!, "vcard_phone")}`);
      if (email) lines.push(`EMAIL;TYPE=INTERNET:${email}`);
      if (clean(o.vcard_web)) lines.push(`URL:${escVcard(clean(o.vcard_web))}`);
      lines.push("END:VCARD");
      return lines.join("\r\n");
    }
    case "sepa": {
      // EPC069-12 (versión 002, UTF-8): el BIC es opcional dentro del EEE.
      const name = clean(o.sepa_beneficiario);
      if (!name) invalid("beneficiary_missing");
      if (name.length > 70) invalid("beneficiary_long");
      const iban = normalizeIban(o.sepa_iban ?? "");
      if (!iban) invalid("iban_invalid");
      const bic = clean(o.sepa_bic).toUpperCase().replace(/\s/g, "");
      if (bic && !isBic(bic)) invalid("bic_invalid");
      const value = amount(o.sepa_importe);
      const purpose = clean(o.sepa_concepto);
      if (purpose.length > 140) invalid("purpose_long");
      const lines = ["BCD", "002", "1", "SCT", bic, name, iban!, value ? `EUR${value}` : "", "", "", purpose];
      while (lines[lines.length - 1] === "") lines.pop();
      const payload = lines.join("\n");
      if (new TextEncoder().encode(payload).length > 331) invalid("epc_too_long");
      return payload;
    }
    case "paypal": {
      const account = clean(o.paypal_cuenta).replace(/^(?:https?:\/\/)?(?:www\.)?paypal\.me\//i, "").replace(/\/+$/, "");
      if (!account) invalid("paypal_missing");
      const currency = clean(o.paypal_moneda || "EUR").toUpperCase();
      if (!/^[A-Z]{3}$/.test(currency)) invalid("currency_invalid");
      const value = amount(o.paypal_importe);
      if (account.includes("@")) {
        if (!EMAIL.test(account)) invalid("email_invalid");
        const q = new URLSearchParams({ cmd: "_xclick", business: account, currency_code: currency });
        if (value) q.set("amount", value);
        return `https://www.paypal.com/cgi-bin/webscr?${q.toString()}`;
      }
      if (!/^[A-Za-z0-9]{1,20}$/.test(account)) invalid("paypal_id_invalid");
      return `https://paypal.me/${account}${value ? `/${value}${currency}` : ""}`;
    }
    case "email": {
      const to = clean(o.email_para);
      if (!EMAIL.test(to)) invalid("email_invalid");
      const q: string[] = [];
      if (clean(o.email_asunto)) q.push(`subject=${encodeURIComponent(clean(o.email_asunto))}`);
      if ((o.email_mensaje ?? "").trim()) q.push(`body=${encodeURIComponent(o.email_mensaje!)}`);
      return `mailto:${to}${q.length ? `?${q.join("&")}` : ""}`;
    }
    case "telefono":
      return `tel:${phone(o.telefono_numero ?? "", "phone")}`;
    case "sms":
      return `SMSTO:${phone(o.sms_numero ?? "", "sms_phone")}:${o.sms_mensaje ?? ""}`;
    case "evento": {
      const title = clean(o.evento_titulo);
      if (!title) invalid("event_title_missing");
      const allDay = Boolean(o.evento_todo_el_dia);
      const start = icalDate(o.evento_inicio ?? "", allDay);
      let end = clean(o.evento_fin) ? icalDate(o.evento_fin!, allDay) : allDay ? nextDay(start) : "";
      if (allDay && end === start) end = nextDay(start);
      if (end && end < start) invalid("event_end_before");
      const esc = (v: string) => v.replace(/\\/g, "\\\\").replace(/([,;])/g, "\\$1").replace(/\r?\n/g, "\\n");
      const lines = ["BEGIN:VEVENT", `SUMMARY:${esc(title)}`, allDay ? `DTSTART;VALUE=DATE:${start}` : `DTSTART:${start}`];
      if (end) lines.push(allDay ? `DTEND;VALUE=DATE:${end}` : `DTEND:${end}`);
      if (clean(o.evento_lugar)) lines.push(`LOCATION:${esc(clean(o.evento_lugar))}`);
      if ((o.evento_descripcion ?? "").trim()) lines.push(`DESCRIPTION:${esc(o.evento_descripcion!.trim())}`);
      lines.push("END:VEVENT");
      return lines.join("\r\n");
    }
    default:
      return invalid("type_invalid");
  }
}

// ——— Modos de codificación (A.1, «Técnico») ———

const ALNUM = /^[0-9A-Z $%*+\-./:]*$/;

let sjis: Map<string, number> | null = null;

/** Tabla Unicode → Shift_JIS de los caracteres de doble byte que admite el modo Kanji (0x8140–0x9FFC y 0xE040–0xEBBF). */
export function sjisTable(): Map<string, number> {
  if (sjis) return sjis;
  const table = new Map<string, number>();
  const decoder = new TextDecoder("shift_jis", { fatal: true });
  const ranges: [number, number][] = [[0x81, 0x9f], [0xe0, 0xeb]];
  for (const [from, to] of ranges) {
    for (let hi = from; hi <= to; hi += 1) {
      for (let lo = 0x40; lo <= 0xfc; lo += 1) {
        if (lo === 0x7f) continue;
        const code = (hi << 8) | lo;
        if (code > 0xebbf) continue;
        try {
          const ch = decoder.decode(new Uint8Array([hi, lo]));
          if (ch.length === 1 && !table.has(ch)) table.set(ch, code);
        } catch {
          // Código sin carácter asignado.
        }
      }
    }
  }
  sjis = table;
  return table;
}

/** Comprueba que el contenido cabe en el modo elegido; si no, lanza QrInputError (mode_numeric, mode_alphanumeric o mode_kanji). */
export function checkMode(payload: string, mode: QrMode): void {
  if (mode === "numerico" && !/^\d+$/.test(payload)) invalid("mode_numeric");
  if (mode === "alfanumerico" && !ALNUM.test(payload)) invalid("mode_alphanumeric");
  if (mode === "kanji") {
    const table = sjisTable();
    for (const ch of payload) if (!table.has(ch)) invalid("mode_kanji", { ch });
  }
}

/** Bytes Shift_JIS del texto (para el modo Kanji de qrcode-generator). */
export function toSjisBytes(text: string): number[] {
  const table = sjisTable();
  const out: number[] = [];
  for (const ch of text) {
    const code = table.get(ch);
    if (code === undefined) invalid("mode_kanji", { ch });
    out.push(code! >> 8, code! & 0xff);
  }
  return out;
}

/** Tipo de contenido de un código leído (para los avisos de leer-codigo-qr). */
export type QrKind = "enlace" | "wifi" | "vcard" | "evento" | "correo" | "telefono" | "sms" | "sepa" | "texto";

export function classifyPayload(text: string): QrKind {
  if (/^https?:\/\//i.test(text)) return "enlace";
  if (/^WIFI:/i.test(text)) return "wifi";
  if (/^BEGIN:VCARD/i.test(text) || /^MECARD:/i.test(text)) return "vcard";
  if (/^BEGIN:(VEVENT|VCALENDAR)/i.test(text)) return "evento";
  if (/^mailto:/i.test(text) || /^MATMSG:/i.test(text)) return "correo";
  if (/^tel:/i.test(text)) return "telefono";
  if (/^(SMSTO|sms):/i.test(text)) return "sms";
  if (/^BCD\r?\n/.test(text)) return "sepa";
  return "texto";
}
