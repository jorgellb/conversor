// crear-factura (A.2, F4-E1): el PDF de la factura con pdf-lib (el cálculo y las validaciones, en invoice-calc.ts). Todo
// en el navegador: los datos de la factura no salen del equipo.
import { PDFDocument, rgb, type PDFFont, type PDFImage, type PDFPage } from "@cantoo/pdf-lib";

import { ToolError, type ToolResult } from "./common";
import { computeTotals, EXEMPTION_TEXT, formatMoney, invoiceProblems, round2, validateIban, type Invoice, type InvoiceTemplate, type Logo,
  type Party } from "./invoice-calc";
import { embedFont, encodable, type FontLoader } from "./pdfutil";

export * from "./invoice-calc";

const TEXTS = {
  es: {
    title: "FACTURA", number: "Número", date: "Fecha", operation: "Fecha de la operación", due: "Vencimiento", issuer: "Emisor",
    customer: "Cliente", taxId: "NIF", description: "Concepto", quantity: "Cant.", unit: "Unidad", price: "Precio", discount: "Dto.",
    vat: "IVA", amount: "Importe", base: "Base imponible", vatAt: "IVA {r} %", surchargeAt: "Recargo de equivalencia {r} %",
    irpfAt: "Retención IRPF {r} %", total: "Total factura", payable: "Total a pagar", payment: "Forma de pago", iban: "IBAN",
    notes: "Observaciones", page: "Página {n} de {t}", file: "factura", vatEur: "Cuota de IVA en euros (1 {c} = {r} EUR)",
    continued: "Factura {n} (continuación)", exemption: "Mención del IVA",
  },
  en: {
    title: "INVOICE", number: "Number", date: "Date", operation: "Date of supply", due: "Due date", issuer: "From", customer: "Bill to",
    taxId: "Tax ID", description: "Description", quantity: "Qty", unit: "Unit", price: "Price", discount: "Disc.", vat: "VAT",
    amount: "Amount", base: "Taxable base", vatAt: "VAT {r} %", surchargeAt: "Equivalence surcharge {r} %",
    irpfAt: "Income tax withholding {r} %", total: "Invoice total", payable: "Amount due", payment: "Payment method", iban: "IBAN",
    notes: "Notes", page: "Page {n} of {t}", file: "invoice", vatEur: "VAT amount in euros (1 {c} = {r} EUR)",
    continued: "Invoice {n} (continued)", exemption: "VAT statement",
  },
};

const ACCENT: Record<InvoiceTemplate, [number, number, number]> = { clasica: [0.2, 0.2, 0.2], moderna: [0.12, 0.31, 0.64], minima: [0.35, 0.35, 0.35] };
const W = 595.28, H = 841.89, M = 42, BOTTOM = M + 30;
// Columnas: borde derecho de las numéricas y anchura disponible de cada una (las cifras se encogen para caber).
const COL = { desc: M, descW: 218, qty: 296, qtyW: 36, unit: 302, unitW: 42, price: 400, priceW: 52, disc: 434, discW: 30, vat: 466, vatW: 28,
  amount: W - M, amountW: 82 };

function formatNumber(value: number, locale: "es" | "en", digits = 2): string {
  return new Intl.NumberFormat(locale === "en" ? "en-GB" : "es-ES", { maximumFractionDigits: digits }).format(value);
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

/** Precio unitario con todos sus decimales (hasta 6), para que cantidad × precio cuadre con el importe (art. 6.1.g). */
function formatPrice(value: number, currency: string, locale: "es" | "en"): string {
  try {
    return new Intl.NumberFormat(locale === "en" ? "en-GB" : "es-ES", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
  } catch {
    return `${value} ${currency}`;
  }
}

/** Caracteres que la fuente no tiene (con fontkit, `encodeText` no falla: dibujaría cuadros vacíos). */
export function missingGlyphs(font: PDFFont, value: string): string[] {
  const fk = (font as unknown as { embedder?: { font?: { hasGlyphForCodePoint?: (cp: number) => boolean } } }).embedder?.font;
  if (!fk?.hasGlyphForCodePoint) return [];
  const missing = new Set<string>();
  for (const ch of value) {
    const cp = ch.codePointAt(0)!;
    if (cp > 0x20 && !fk.hasGlyphForCodePoint(cp)) missing.add(ch);
  }
  return [...missing];
}

/** Líneas que caben en `width`, partiendo también las palabras que solas no caben (URL, correos). */
export function wrapHard(value: string, font: PDFFont, size: number, width: number): string[] {
  const out: string[] = [];
  for (const paragraph of value.split(/\r?\n/)) {
    let line = "";
    for (const word of paragraph.split(/(\s+)/)) {
      if (!word) continue;
      const candidate = line + word;
      if (font.widthOfTextAtSize(encodable(font, candidate.trimEnd()), size) <= width) {
        line = candidate;
        continue;
      }
      if (line.trim()) out.push(line.trimEnd());
      let rest = word.trimStart();
      while (rest && font.widthOfTextAtSize(encodable(font, rest), size) > width) {
        let n = rest.length;
        while (n > 1 && font.widthOfTextAtSize(encodable(font, rest.slice(0, n)), size) > width) n -= 1;
        out.push(rest.slice(0, n));
        rest = rest.slice(n);
      }
      line = rest;
    }
    out.push(line.trimEnd());
  }
  return out;
}

interface Ctx {
  doc: PDFDocument;
  page: PDFPage;
  font: PDFFont;
  bold: PDFFont;
  y: number;
  accent: [number, number, number];
}

function text(ctx: Ctx, value: string, x: number, y: number, size = 9, font = ctx.font, color: [number, number, number] = [0.1, 0.1, 0.1]) {
  ctx.page.drawText(encodable(font, value), { x, y, size, font, color: rgb(...color) });
}

/** Alineado a la derecha y encogido (hasta 5,5 pt) si no cabe en `width`. */
function right(ctx: Ctx, value: string, xRight: number, y: number, size = 9, font = ctx.font, width = Infinity) {
  const v = encodable(font, value);
  let s = size;
  while (s > 5.5 && font.widthOfTextAtSize(v, s) > width) s -= 0.25;
  ctx.page.drawText(v, { x: xRight - font.widthOfTextAtSize(v, s), y, size: s, font, color: rgb(0.1, 0.1, 0.1) });
}

function left(ctx: Ctx, value: string, x: number, y: number, size: number, width: number) {
  const v = encodable(ctx.font, value);
  let s = size;
  while (s > 5.5 && ctx.font.widthOfTextAtSize(v, s) > width) s -= 0.25;
  text(ctx, v, x, y, s);
}

function partyLines(p: Party, t: (typeof TEXTS)["es"]): string[] {
  return [p.name, p.taxId ? `${t.taxId}: ${p.taxId}` : "", p.address, [p.postcode, p.city].filter(Boolean).join(" "),
    p.country && p.country !== "ES" ? p.country : "", p.email ?? ""].filter((l) => l && l.trim());
}

/** El PDF de la factura (A4) con su plantilla, el logotipo y los totales de `computeTotals`. */
export async function invoicePdf(inv: Invoice, logo?: Logo, loader?: FontLoader): Promise<Uint8Array> {
  const t = TEXTS[inv.locale] ?? TEXTS.es;
  const totals = computeTotals(inv);
  const doc = await PDFDocument.create();
  doc.setTitle(`${t.title} ${inv.number}`);
  doc.setAuthor(inv.issuer.name);
  doc.setCreator("crear-factura");
  const font = await embedFont(doc, "sans", loader, "regular");
  const bold = await embedFont(doc, "sans", loader, "bold");
  const all = [inv.number, inv.notes, inv.paymentMethod, ...[inv.issuer, inv.customer].flatMap((p) => partyLines(p, t)),
    ...inv.lines.flatMap((l) => [l.description, l.unit])].filter(Boolean).join(" ");
  const missing = missingGlyphs(font, all);
  if (missing.length) throw new ToolError("UNSUPPORTED_FORMAT", `glyphs:${missing.slice(0, 10).join("")}`);
  const template = inv.template ?? "clasica";
  const ctx: Ctx = { doc, page: doc.addPage([W, H]), font, bold, y: H - M, accent: ACCENT[template] };
  const money = (v: number) => formatMoney(v, inv.currency, inv.locale);
  let image: PDFImage | null = null;
  if (logo) {
    try {
      image = logo.format === "png" ? await doc.embedPng(logo.data) : await doc.embedJpg(logo.data);
    } catch {
      throw new ToolError("UNSUPPORTED_FORMAT", "logotipo");
    }
  }
  const band = () => {
    if (template === "moderna") ctx.page.drawRectangle({ x: 0, y: H - 18, width: W, height: 18, color: rgb(...ctx.accent) });
  };

  // Cabecera: logotipo, título y datos de la factura.
  band();
  const top = H - M;
  if (image) {
    const scale = Math.min(140 / image.width, 60 / image.height, 1);
    ctx.page.drawImage(image, { x: M, y: top - image.height * scale, width: image.width * scale, height: image.height * scale });
  }
  right(ctx, t.title, W - M, top - 16, 20, bold);
  const meta: [string, string][] = [[t.number, inv.number], [t.date, formatDate(inv.issueDate)]];
  if (inv.operationDate && inv.operationDate !== inv.issueDate) meta.push([t.operation, formatDate(inv.operationDate)]);
  if (inv.dueDate) meta.push([t.due, formatDate(inv.dueDate)]);
  meta.forEach(([k, v], i) => right(ctx, `${k}: ${v}`, W - M, top - 36 - i * 12, 9, font, 260));
  const y0 = top - 48 - meta.length * 12;

  // Emisor y cliente.
  const colW = (W - 2 * M - 20) / 2;
  const blocks: [string, Party, number][] = [[t.issuer, inv.issuer, M], [t.customer, inv.customer, M + colW + 20]];
  let lowest = y0;
  for (const [label, party, x] of blocks) {
    text(ctx, label.toUpperCase(), x, y0, 8, bold, ctx.accent);
    let y = y0 - 14;
    partyLines(party, t).forEach((line, i) => {
      for (const part of wrapHard(line, i === 0 ? bold : font, 9.5, colW)) {
        text(ctx, part, x, y, 9.5, i === 0 ? bold : font);
        y -= 12;
      }
    });
    lowest = Math.min(lowest, y);
  }
  ctx.y = lowest - 18;

  // Conceptos.
  const header = () => {
    const y = ctx.y;
    if (template !== "minima") ctx.page.drawRectangle({ x: M - 4, y: y - 5, width: W - 2 * M + 8, height: 17, color: rgb(0.94, 0.95, 0.97) });
    text(ctx, t.description, COL.desc, y, 8.5, bold);
    right(ctx, t.quantity, COL.qty, y, 8.5, bold);
    text(ctx, t.unit, COL.unit, y, 8.5, bold);
    right(ctx, t.price, COL.price, y, 8.5, bold);
    right(ctx, t.discount, COL.disc, y, 8.5, bold);
    right(ctx, t.vat, COL.vat, y, 8.5, bold);
    right(ctx, t.amount, COL.amount, y, 8.5, bold);
    ctx.y -= 20;
  };
  /** Página nueva con el número de la factura arriba; la cabecera de la tabla solo si siguen conceptos. */
  const newPage = (withHeader: boolean) => {
    ctx.page = doc.addPage([W, H]);
    band();
    ctx.y = H - M - 6;
    text(ctx, t.continued.replace("{n}", inv.number), M, ctx.y, 8.5, bold, ctx.accent);
    ctx.y -= 22;
    if (withHeader) header();
  };
  header();
  inv.lines.forEach((line, i) => {
    const lt = totals.lines[i];
    const desc = wrapHard(line.description, font, 9, COL.descW);
    if (ctx.y - Math.min(desc.length, 3) * 11 - 6 < BOTTOM) newPage(true);
    const y = ctx.y;
    right(ctx, formatNumber(line.quantity, inv.locale, 6), COL.qty, y, 9, font, COL.qtyW);
    left(ctx, line.unit, COL.unit, y, 9, COL.unitW);
    right(ctx, formatPrice(line.price, inv.currency, inv.locale), COL.price, y, 9, font, COL.priceW);
    right(ctx, line.discount ? `${formatNumber(line.discount, inv.locale)} %` : "", COL.disc, y, 9, font, COL.discW);
    right(ctx, `${formatNumber(line.vat, inv.locale)} %`, COL.vat, y, 9, font, COL.vatW);
    right(ctx, money(lt.net), COL.amount, y, 9, font, COL.amountW);
    // La descripción sigue en la página siguiente si no cabe (un concepto muy largo no se sale del papel).
    for (const part of desc) {
      if (ctx.y < BOTTOM) newPage(true);
      text(ctx, part, COL.desc, ctx.y, 9);
      ctx.y -= 11;
    }
    ctx.y -= 6;
    if (template === "clasica") {
      const ly = ctx.y + 9;
      ctx.page.drawLine({ start: { x: M - 4, y: ly }, end: { x: W - M + 4, y: ly }, thickness: 0.4, color: rgb(0.8, 0.8, 0.8) });
    }
  });

  // Totales.
  const rows: [string, string, boolean][] = [];
  for (const g of totals.groups) {
    rows.push([`${t.base} (${formatNumber(g.rate, inv.locale)} %)`, money(g.base), false]);
    rows.push([t.vatAt.replace("{r}", formatNumber(g.rate, inv.locale)), money(g.tax), false]);
    if (g.surchargeRate) rows.push([t.surchargeAt.replace("{r}", formatNumber(g.surchargeRate, inv.locale)), money(g.surcharge), false]);
  }
  rows.push([t.total, money(totals.total), true]);
  if (inv.irpf) {
    rows.push([t.irpfAt.replace("{r}", formatNumber(inv.irpf, inv.locale)), money(-totals.irpf), false]);
    rows.push([t.payable, money(totals.payable), true]);
  }
  if (inv.currency !== "EUR" && inv.exchangeRate) {
    rows.push([t.vatEur.replace("{c}", inv.currency).replace("{r}", formatNumber(inv.exchangeRate, inv.locale, 6)),
      formatMoney(round2(totals.tax * inv.exchangeRate), "EUR", inv.locale), false]);
  }
  if (ctx.y - rows.length * 15 - 10 < BOTTOM) newPage(false);
  ctx.y -= 8;
  for (const [label, value, strong] of rows) {
    right(ctx, label, 430, ctx.y, strong ? 10 : 9, strong ? bold : font, 300);
    right(ctx, value, W - M, ctx.y, strong ? 10 : 9, strong ? bold : font, 110);
    ctx.y -= strong ? 16 : 13;
  }

  // Mención del IVA 0 %, pago y observaciones (se parten entre páginas si hace falta).
  const extra: [string, string][] = [];
  if (inv.exemption && inv.lines.some((l) => l.vat === 0)) extra.push([t.exemption, EXEMPTION_TEXT[inv.exemption][inv.locale]]);
  if (inv.paymentMethod?.trim()) extra.push([t.payment, inv.paymentMethod.trim()]);
  if (inv.iban?.trim()) extra.push([t.iban, validateIban(inv.iban).normalized]);
  if (inv.notes?.trim()) extra.push([t.notes, inv.notes.trim()]);
  ctx.y -= 10;
  for (const [label, value] of extra) {
    if (ctx.y - 24 < BOTTOM) newPage(false);
    text(ctx, label.toUpperCase(), M, ctx.y, 8, bold, ctx.accent);
    ctx.y -= 12;
    for (const part of wrapHard(value, font, 9, W - 2 * M)) {
      if (ctx.y < BOTTOM) newPage(false);
      text(ctx, part, M, ctx.y, 9);
      ctx.y -= 12;
    }
    ctx.y -= 6;
  }

  const pages = doc.getPages();
  pages.forEach((p, i) => {
    const label = t.page.replace("{n}", String(i + 1)).replace("{t}", String(pages.length));
    const v = encodable(font, label);
    p.drawText(v, { x: W - M - font.widthOfTextAtSize(v, 7.5), y: M / 2, size: 7.5, font, color: rgb(0.45, 0.45, 0.45) });
  });
  return doc.save({ useObjectStreams: true });
}

export interface CrearFacturaOptions {
  invoice: Invoice;
  logo?: Logo;
}

/** crear-factura: comprueba la factura y devuelve su PDF. */
export async function crearFactura(options: CrearFacturaOptions, loader?: FontLoader): Promise<ToolResult> {
  const inv = options.invoice;
  if (!inv) throw new ToolError("INVALID_OPTIONS", "factura");
  const problems = invoiceProblems(inv);
  if (problems.length) throw new ToolError("INVALID_OPTIONS", problems.join(","));
  const bytes = await invoicePdf(inv, options.logo, loader);
  const t = TEXTS[inv.locale] ?? TEXTS.es;
  const safe = inv.number.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "1";
  return { outputs: [{ name: `${t.file}-${safe}.pdf`, bytes, mime: "application/pdf" }], notes: [] };
}
