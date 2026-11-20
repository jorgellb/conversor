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
  /** Para la factura electrónica (crear-factura-electronica, D-205). */
  province?: string;
  phone?: string;
  contact?: string;
  endpointScheme?: string;
  endpointId?: string;
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

/** Causa de un IVA del 0 % (RD 1619/2012, art. 6.1.j): la factura cita el precepto. */
export type Exemption = "art20" | "art21" | "art25" | "isp" | "nosujeta";

/** Texto que se imprime para cada causa (es y en). */
export const EXEMPTION_TEXT: Record<Exemption, { es: string; en: string }> = {
  art20: { es: "Operación exenta de IVA (art. 20 de la Ley 37/1992).", en: "VAT-exempt supply (art. 20 of Spanish Law 37/1992)." },
  art21: { es: "Exportación exenta de IVA (art. 21 de la Ley 37/1992).", en: "VAT-exempt export (art. 21 of Spanish Law 37/1992)." },
  art25: { es: "Entrega intracomunitaria exenta de IVA (art. 25 de la Ley 37/1992).", en: "VAT-exempt intra-Community supply (art. 25 of Spanish Law 37/1992)." },
  isp: { es: "Inversión del sujeto pasivo (art. 84.Uno.2.º de la Ley 37/1992).", en: "Reverse charge (art. 84.Uno.2 of Spanish Law 37/1992)." },
  nosujeta: { es: "Operación no sujeta a IVA (art. 7 de la Ley 37/1992).", en: "Supply not subject to VAT (art. 7 of Spanish Law 37/1992)." },
};

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
  /** Fecha de la operación, si no es la de expedición (art. 6.1.f). */
  operationDate?: string;
  /** Causa del IVA 0 % (obligatoria si alguna línea lo lleva). */
  exemption?: Exemption;
  /** Euros por unidad de la moneda: con otra moneda, la cuota de IVA va también en euros (art. 12.1). */
  exchangeRate?: number;
}

export interface Logo {
  data: Uint8Array;
  format: "png" | "jpg";
}

/** Recargo de equivalencia de cada tipo de IVA (art. 161 de la Ley 37/1992). */
export const SURCHARGE: Record<number, number> = { 21: 5.2, 10: 1.4, 5: 0.62, 4: 0.5, 2: 0.26, 0: 0 };

/** Redondeo a céntimos (EN 16931: cada importe se redondea a 2 decimales) sin el error de 1.005 * 100. */
export function round2(value: number): number {
  const sign = value < 0 ? -1 : 1;
  return (sign * Math.round(Number((Math.abs(value) * 100).toFixed(8)))) / 100 + 0;  // + 0: sin «-0»
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
  // Sin país (o uno que no es un código ISO) se trata como España: no basta con vaciar el país para saltarse la comprobación.
  const c = /^[A-Za-z]{2}$/.test(country.trim()) ? country.trim().toUpperCase() : "ES";
  if (c !== "ES") {
    return { ok: /^[A-Z0-9]{4,20}$/.test(id) && /\d/.test(id), kind: "foreign", normalized: id };
  }
  if (id.startsWith("ES") && id.length === 11) id = id.slice(2);
  if (/^0{8}/.test(id)) return { ok: false, normalized: id };
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
  if (rest !== 1) return { ok: false, normalized: iban };
  if (iban.startsWith("ES") && !spanishCcc(iban.slice(4))) return { ok: false, normalized: iban };
  return { ok: true, normalized: iban.replace(/(.{4})/g, "$1 ").trim() };
}

/** Dígitos de control del CCC español (entidad, oficina, DC y cuenta) dentro del IBAN. */
function spanishCcc(ccc: string): boolean {
  if (!/^\d{20}$/.test(ccc)) return false;
  const weights = [1, 2, 4, 8, 5, 10, 9, 7, 3, 6];
  const dc = (digits: string) => {
    const sum = digits.split("").reduce((acc, d, i) => acc + Number(d) * weights[i], 0);
    const v = 11 - (sum % 11);
    return v === 11 ? 0 : v === 10 ? 1 : v;
  };
  return `${dc("00" + ccc.slice(0, 8))}${dc(ccc.slice(10))}` === ccc.slice(8, 10);
}

/** Problemas que impiden emitir la factura (los textos los pone la página con estas claves). */
/** Fecha ISO que existe de verdad (2026-02-31 no). */
export function isDate(value: string | undefined): boolean {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
}

/** Elementos obligatorios de una factura completa (RD 1619/2012, art. 6) y coherencia de los importes. */
export function invoiceProblems(inv: Invoice): string[] {
  const out: string[] = [];
  const zero = inv.lines.some((l) => l.vat === 0);
  if (!inv.number.trim()) out.push("number");
  if (!isDate(inv.issueDate)) out.push("issueDate");
  if (inv.dueDate && (!isDate(inv.dueDate) || inv.dueDate < inv.issueDate)) out.push("dueDate");
  if (inv.operationDate && !isDate(inv.operationDate)) out.push("operationDate");
  if (!inv.issuer.name?.trim()) out.push("issuerName");
  if (!validateTaxId(inv.issuer.taxId ?? "", inv.issuer.country ?? "ES").ok) out.push("issuerTaxId");
  if (!inv.issuer.address?.trim() || !inv.issuer.city?.trim()) out.push("issuerAddress");
  if (!inv.customer.name?.trim()) out.push("customerName");
  const customerId = (inv.customer.taxId ?? "").trim();
  if (customerId && !validateTaxId(customerId, inv.customer.country ?? "ES").ok) out.push("customerTaxId");
  // Con retención, recargo, entrega intracomunitaria o inversión del sujeto pasivo, el cliente es empresa o profesional.
  if (!customerId && (inv.irpf > 0 || inv.surcharge || (zero && (inv.exemption === "art25" || inv.exemption === "isp")))) out.push("customerTaxIdRequired");
  if (zero && !inv.exemption) out.push("exemption");
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
  if (inv.currency !== "EUR" && !((inv.exchangeRate ?? 0) > 0)) out.push("exchangeRate");
  for (const p of [inv.issuer, inv.customer]) {
    if (p.country && !/^[A-Z]{2}$/.test(p.country)) {
      out.push("country");
      break;
    }
  }
  const lines = inv.lines.filter((l) => Number.isFinite(l.quantity) && Number.isFinite(l.price));
  if (lines.length === inv.lines.length && inv.lines.length && computeTotals(inv).payable < 0) out.push("negative");
  return out;
}

export function formatMoney(value: number, currency: string, locale: "es" | "en"): string {
  try {
    return new Intl.NumberFormat(locale === "en" ? "en-GB" : "es-ES", { style: "currency", currency, minimumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}


/** Número escrito como en el idioma de la página: en «es», «1.500» y «1.234,56» (punto de millares, coma decimal); en
 *  «en», «1,500.5». Un «0.125» o un «12.5» sueltos son siempre decimales. */
export function parseAmount(raw: string, locale: "es" | "en" = "es"): number {
  let v = raw.trim().replace(/[\s\u00a0]/g, "");
  if (!v) return NaN;
  if (locale === "en") {
    v = v.replace(/,(?=\d{3}(\D|$))/g, "");
  } else if (v.includes(",")) {
    v = v.replace(/\./g, "").replace(",", ".");
  } else if (/^-?[1-9]\d{0,2}(\.\d{3})+$/.test(v)) {
    v = v.replace(/\./g, "");
  }
  return /^-?\d+(\.\d+)?$/.test(v) ? Number(v) : NaN;
}
