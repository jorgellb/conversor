// crear-factura (A.2, F4-E1): cálculo con los redondeos de EN 16931 y validación de NIF, NIE, CIF e IBAN, sin
// dependencias, para la vista previa en vivo de la página (el PDF, con pdf-lib, está en invoice.ts).
export interface Party {
  name: string;
  taxId: string;
  address: string;
  postcode?: string;
  city?: string;
  /** ISO 3166-1 alfa-2. */
  country: string;
  email?: string;
}

export interface InvoiceLine {
  description: string;
  quantity: number;
  unit: string;
  /** Precio unitario sin IVA. */
  price: number;
  /** Descuento en %. */
  discount: number;
  /** Tipo de IVA en %. */
  vat: number;
}

export type InvoiceTemplate = "clasica" | "moderna" | "minima";

export interface Invoice {
  number: string;
  issueDate: string;
  dueDate?: string;
  issuer: Party;
  customer: Party;
  lines: InvoiceLine[];
  /** Recargo de equivalencia (comercio minorista): se añade a cada tipo de IVA. */
  surcharge: boolean;
  /** Retención de IRPF en %. */
  irpf: number;
  currency: string;
  locale: "es" | "en";
  notes?: string;
  paymentMethod?: string;
  iban?: string;
  template?: InvoiceTemplate;
}

export interface Logo {
  data: Uint8Array;
  format: "png" | "jpg";
}

/** Recargo de equivalencia de cada tipo de IVA (art. 161 de la Ley 37/1992). */
export const SURCHARGE: Record<number, number> = { 21: 5.2, 10: 1.4, 4: 0.5, 0: 0 };

/** Redondeo a céntimos (EN 16931: cada importe se redondea a 2 decimales) sin el error de 1.005 * 100. */
export function round2(value: number): number {
  const sign = value < 0 ? -1 : 1;
  return (sign * Math.round(Number((Math.abs(value) * 100).toFixed(8)))) / 100;
}

export interface LineTotal {
  gross: number;
  discount: number;
  /** BT-131: importe neto de la línea. */
  net: number;
}

export interface TaxGroup {
  rate: number;
  /** BT-116: base imponible del tipo. */
  base: number;
  /** BT-117: cuota del tipo. */
  tax: number;
  surchargeRate: number;
  surcharge: number;
}

export interface InvoiceTotals {
  lines: LineTotal[];
  groups: TaxGroup[];
  /** BT-106: suma de los netos de las líneas. */
  net: number;
  /** BT-110: IVA total. */
  tax: number;
  surcharge: number;
  /** BT-112: total con IVA (y recargo). */
  total: number;
  irpf: number;
  /** BT-115: importe a pagar. */
  payable: number;
}

export function lineTotal(line: InvoiceLine): LineTotal {
  const gross = round2(line.quantity * line.price);
  const discount = round2((gross * (line.discount || 0)) / 100);
  return { gross, discount, net: round2(gross - discount) };
}

/** Totales con la regla de EN 16931: la cuota de cada tipo se calcula sobre la suma de las bases, no línea a línea. */
export function computeTotals(inv: Pick<Invoice, "lines" | "surcharge" | "irpf">): InvoiceTotals {
  const lines = inv.lines.map(lineTotal);
  const byRate = new Map<number, number>();
  inv.lines.forEach((line, i) => byRate.set(line.vat, round2((byRate.get(line.vat) ?? 0) + lines[i].net)));
  const groups: TaxGroup[] = [...byRate.entries()].sort((a, b) => b[0] - a[0]).map(([rate, base]) => {
    const surchargeRate = inv.surcharge ? (SURCHARGE[rate] ?? 0) : 0;
    return { rate, base, tax: round2((base * rate) / 100), surchargeRate, surcharge: round2((base * surchargeRate) / 100) };
  });
  const net = round2(lines.reduce((s, l) => s + l.net, 0));
  const tax = round2(groups.reduce((s, g) => s + g.tax, 0));
  const surcharge = round2(groups.reduce((s, g) => s + g.surcharge, 0));
  const total = round2(net + tax + surcharge);
  const irpf = round2((net * (inv.irpf || 0)) / 100);
  return { lines, groups, net, tax, surcharge, total, irpf, payable: round2(total - irpf) };
}

// --- NIF, NIE, CIF e IBAN -------------------------------------------------------------------------------------------

const DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE";

export type TaxIdKind = "nif" | "nie" | "cif" | "foreign";

/** Comprueba el dígito o la letra de control de un NIF, NIE o CIF español (con o sin prefijo «ES»); fuera de España,
 *  solo la forma. */
export function validateTaxId(raw: string, country = "ES"): { ok: boolean; kind?: TaxIdKind; normalized: string } {
  let id = raw.toUpperCase().replace(/[\s.-]/g, "");
  if (country.toUpperCase() !== "ES") {
    return { ok: /^[A-Z0-9]{2,20}$/.test(id), kind: "foreign", normalized: id };
  }
  if (id.startsWith("ES") && id.length === 11) id = id.slice(2);
  if (/^\d{8}[A-Z]$/.test(id)) {
    return { ok: DNI_LETTERS[Number(id.slice(0, 8)) % 23] === id[8], kind: "nif", normalized: id };
  }
  if (/^[XYZ]\d{7}[A-Z]$/.test(id)) {
    const n = Number(String("XYZ".indexOf(id[0])) + id.slice(1, 8));
    return { ok: DNI_LETTERS[n % 23] === id[8], kind: "nie", normalized: id };
  }
  if (/^[KLM]\d{7}[A-Z]$/.test(id)) {
    return { ok: DNI_LETTERS[Number(id.slice(1, 8)) % 23] === id[8], kind: "nif", normalized: id };
  }
  if (/^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$/.test(id)) {
    const digits = id.slice(1, 8).split("").map(Number);
    let sum = 0;
    digits.forEach((d, i) => {
      if (i % 2 === 1) sum += d;
      else {
        const doubled = d * 2;
        sum += Math.floor(doubled / 10) + (doubled % 10);
      }
    });
    const control = (10 - (sum % 10)) % 10;
    const letter = "JABCDEFGHI"[control];
    const given = id[8];
    const ok = "PQRSNW".includes(id[0]) ? given === letter : "ABEH".includes(id[0]) ? given === String(control) : given === letter || given === String(control);
    return { ok, kind: "cif", normalized: id };
  }
  return { ok: false, normalized: id };
}

const IBAN_LENGTH: Record<string, number> = {
  ES: 24, PT: 25, FR: 27, DE: 22, IT: 27, NL: 18, BE: 16, AT: 20, IE: 22, LU: 20, GB: 22, CH: 21, AD: 24, MC: 27, PL: 28, SE: 24,
  DK: 18, FI: 18, NO: 15, CZ: 24, GR: 27, RO: 24, HU: 28, SK: 24, SI: 19, HR: 21, BG: 22, LT: 20, LV: 21, EE: 20, CY: 28, MT: 31,
};

/** IBAN con la comprobación ISO 13616 (mod 97) y la longitud de su país cuando se conoce. */
export function validateIban(raw: string): { ok: boolean; normalized: string } {
  const iban = raw.toUpperCase().replace(/\s/g, "");
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/.test(iban)) return { ok: false, normalized: iban };
  const expected = IBAN_LENGTH[iban.slice(0, 2)];
  if (expected && iban.length !== expected) return { ok: false, normalized: iban };
  const moved = iban.slice(4) + iban.slice(0, 4);
  let rest = 0;
  for (const ch of moved) {
    const value = /\d/.test(ch) ? ch : String(ch.charCodeAt(0) - 55);
    for (const digit of value) rest = (rest * 10 + Number(digit)) % 97;
  }
  return { ok: rest === 1, normalized: iban.replace(/(.{4})/g, "$1 ").trim() };
}

/** Problemas que impiden emitir la factura (los textos los pone la página con estas claves). */
export function invoiceProblems(inv: Invoice): string[] {
  const out: string[] = [];
  if (!inv.number.trim()) out.push("number");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(inv.issueDate)) out.push("issueDate");
  if (inv.dueDate && inv.dueDate < inv.issueDate) out.push("dueDate");
  if (!inv.issuer.name.trim()) out.push("issuerName");
  if (!validateTaxId(inv.issuer.taxId, inv.issuer.country).ok) out.push("issuerTaxId");
  if (!inv.customer.name.trim()) out.push("customerName");
  if (inv.customer.taxId.trim() && !validateTaxId(inv.customer.taxId, inv.customer.country).ok) out.push("customerTaxId");
  if (!inv.lines.length) out.push("lines");
  inv.lines.forEach((l, i) => {
    if (!l.description.trim()) out.push(`line${i}.description`);
    if (!Number.isFinite(l.quantity) || l.quantity === 0) out.push(`line${i}.quantity`);
    if (!Number.isFinite(l.price)) out.push(`line${i}.price`);
    if (!(l.discount >= 0 && l.discount <= 100)) out.push(`line${i}.discount`);
    if (!(l.vat >= 0 && l.vat <= 100)) out.push(`line${i}.vat`);
  });
  if (!(inv.irpf >= 0 && inv.irpf <= 50)) out.push("irpf");
  if (inv.iban?.trim() && !validateIban(inv.iban).ok) out.push("iban");
  if (!/^[A-Z]{3}$/.test(inv.currency)) out.push("currency");
  return out;
}

export function formatMoney(value: number, currency: string, locale: "es" | "en"): string {
  try {
    return new Intl.NumberFormat(locale === "en" ? "en-GB" : "es-ES", { style: "currency", currency, minimumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}
