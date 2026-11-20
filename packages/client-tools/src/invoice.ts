// crear-factura (A.2, F4-E1): el PDF de la factura con pdf-lib (el cálculo y las validaciones, en invoice-calc.ts). Todo en el navegador: los datos de la factura no salen del equipo.
import { PDFDocument, rgb, type PDFFont, type PDFImage, type PDFPage } from "@cantoo/pdf-lib";

import { ToolError, type ToolResult } from "./common";
import { wrapText } from "./edit";
import { computeTotals, formatMoney, invoiceProblems, validateIban, type Invoice, type InvoiceTemplate, type Logo, type Party } from "./invoice-calc";
import { embedFont, encodable, type FontLoader } from "./pdfutil";

export * from "./invoice-calc";

// --- PDF -----------------------------------------------------------------------------------------------------------

const TEXTS = {
  es: {
    title: "FACTURA", number: "Número", date: "Fecha", due: "Vencimiento", issuer: "Emisor", customer: "Cliente",
    taxId: "NIF", description: "Concepto", quantity: "Cant.", unit: "Unidad", price: "Precio", discount: "Dto.", vat: "IVA",
    amount: "Importe", base: "Base imponible", vatAt: "IVA {r} %", surchargeAt: "Recargo de equivalencia {r} %",
    irpfAt: "Retención IRPF {r} %", total: "Total factura", payable: "Total a pagar", payment: "Forma de pago",
    iban: "IBAN", notes: "Observaciones", page: "Página {n} de {t}", file: "factura",
  },
  en: {
    title: "INVOICE", number: "Number", date: "Date", due: "Due date", issuer: "From", customer: "Bill to", taxId: "Tax ID",
    description: "Description", quantity: "Qty", unit: "Unit", price: "Price", discount: "Disc.", vat: "VAT", amount: "Amount",
    base: "Taxable base", vatAt: "VAT {r} %", surchargeAt: "Equivalence surcharge {r} %", irpfAt: "Income tax withholding {r} %",
    total: "Invoice total", payable: "Amount due", payment: "Payment method", iban: "IBAN", notes: "Notes",
    page: "Page {n} of {t}", file: "invoice",
  },
};

const ACCENT: Record<InvoiceTemplate, [number, number, number]> = { clasica: [0.2, 0.2, 0.2], moderna: [0.12, 0.31, 0.64], minima: [0.35, 0.35, 0.35] };
const W = 595.28, H = 841.89, M = 42;

function formatNumber(value: number, locale: "es" | "en", digits = 2): string {
  return new Intl.NumberFormat(locale === "en" ? "en-GB" : "es-ES", { maximumFractionDigits: digits }).format(value);
}

function formatDate(iso: string, locale: "es" | "en"): string {
  const [y, m, d] = iso.split("-");
  return y && m && d ? (locale === "en" ? `${d}/${m}/${y}` : `${d}/${m}/${y}`) : iso;
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

function right(ctx: Ctx, value: string, xRight: number, y: number, size = 9, font = ctx.font) {
  const v = encodable(font, value);
  ctx.page.drawText(v, { x: xRight - font.widthOfTextAtSize(v, size), y, size, font, color: rgb(0.1, 0.1, 0.1) });
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

  // Cabecera: banda de color (moderna), logotipo, título y datos de la factura.
  if (template === "moderna") ctx.page.drawRectangle({ x: 0, y: H - 18, width: W, height: 18, color: rgb(...ctx.accent) });
  let top = H - M;
  if (image) {
    const scale = Math.min(140 / image.width, 60 / image.height, 1);
    ctx.page.drawImage(image, { x: M, y: top - image.height * scale, width: image.width * scale, height: image.height * scale });
  }
  right(ctx, t.title, W - M, top - 16, 20, bold);
  const meta: [string, string][] = [[t.number, inv.number], [t.date, formatDate(inv.issueDate, inv.locale)]];
  if (inv.dueDate) meta.push([t.due, formatDate(inv.dueDate, inv.locale)]);
  meta.forEach(([k, v], i) => {
    right(ctx, `${k}: ${v}`, W - M, top - 36 - i * 12, 9);
  });
  top -= 100;

  // Emisor y cliente.
  const colW = (W - 2 * M - 20) / 2;
  const blocks: [string, Party, number][] = [[t.issuer, inv.issuer, M], [t.customer, inv.customer, M + colW + 20]];
  let lowest = top;
  for (const [label, party, x] of blocks) {
    text(ctx, label.toUpperCase(), x, top, 8, bold, ctx.accent);
    let y = top - 14;
    partyLines(party, t).forEach((line, i) => {
      for (const part of wrapText(line, i === 0 ? bold : font, 9.5, colW)) {
        text(ctx, part, x, y, 9.5, i === 0 ? bold : font);
        y -= 12;
      }
    });
    lowest = Math.min(lowest, y);
  }
  ctx.y = lowest - 18;

  // Conceptos.
  const cols = { desc: M, qty: 330, unit: 340, price: 425, disc: 465, vat: 500, amount: W - M };
  const header = () => {
    const y = ctx.y;
    if (template !== "minima") ctx.page.drawRectangle({ x: M - 4, y: y - 5, width: W - 2 * M + 8, height: 17, color: rgb(0.94, 0.95, 0.97) });
    text(ctx, t.description, cols.desc, y, 8.5, bold);
    right(ctx, t.quantity, cols.qty, y, 8.5, bold);
    text(ctx, t.unit, cols.unit, y, 8.5, bold);
    right(ctx, t.price, cols.price, y, 8.5, bold);
    right(ctx, t.discount, cols.disc, y, 8.5, bold);
    right(ctx, t.vat, cols.vat, y, 8.5, bold);
    right(ctx, t.amount, cols.amount, y, 8.5, bold);
    ctx.y -= 20;
  };
  const newPage = () => {
    ctx.page = doc.addPage([W, H]);
    ctx.y = H - M - 10;
    if (template === "moderna") ctx.page.drawRectangle({ x: 0, y: H - 18, width: W, height: 18, color: rgb(...ctx.accent) });
    header();
  };
  header();
  inv.lines.forEach((line, i) => {
    const lt = totals.lines[i];
    const desc = wrapText(line.description, font, 9, cols.qty - cols.desc - 40);
    const need = desc.length * 11 + 6;
    if (ctx.y - need < M + 40) newPage();
    const y = ctx.y;
    desc.forEach((part, j) => text(ctx, part, cols.desc, y - j * 11, 9));
    right(ctx, formatNumber(line.quantity, inv.locale, 4), cols.qty, y, 9);
    text(ctx, line.unit.slice(0, 14), cols.unit, y, 9);
    right(ctx, money(line.price), cols.price, y, 9);
    right(ctx, line.discount ? `${formatNumber(line.discount, inv.locale)} %` : "", cols.disc, y, 9);
    right(ctx, `${formatNumber(line.vat, inv.locale)} %`, cols.vat, y, 9);
    right(ctx, money(lt.net), cols.amount, y, 9);
    ctx.y -= need;
    if (template === "clasica") ctx.page.drawLine({ start: { x: M - 4, y: ctx.y + 3 }, end: { x: W - M + 4, y: ctx.y + 3 }, thickness: 0.4, color: rgb(0.8, 0.8, 0.8) });
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
  if (ctx.y - rows.length * 14 - 20 < M + 40) newPage();
  ctx.y -= 8;
  for (const [label, value, strong] of rows) {
    right(ctx, label, 430, ctx.y, strong ? 10 : 9, strong ? bold : font);
    right(ctx, value, W - M, ctx.y, strong ? 10 : 9, strong ? bold : font);
    ctx.y -= strong ? 16 : 13;
  }

  // Pago y observaciones.
  const extra: [string, string][] = [];
  if (inv.paymentMethod?.trim()) extra.push([t.payment, inv.paymentMethod.trim()]);
  if (inv.iban?.trim()) extra.push([t.iban, validateIban(inv.iban).normalized]);
  if (inv.notes?.trim()) extra.push([t.notes, inv.notes.trim()]);
  ctx.y -= 10;
  for (const [label, value] of extra) {
    const parts = wrapText(value, font, 9, W - 2 * M);
    if (ctx.y - (parts.length + 1) * 12 < M + 20) newPage();
    text(ctx, label.toUpperCase(), M, ctx.y, 8, bold, ctx.accent);
    ctx.y -= 12;
    for (const part of parts) {
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
