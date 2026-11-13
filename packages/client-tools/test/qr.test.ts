import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFDocument, PDFName, PDFRawStream } from "@cantoo/pdf-lib";
import encodePng from "@jsquash/png/encode.js";
import { init as initPng } from "@jsquash/png/decode.js";
import qrcode from "qrcode-generator";
import { describe, expect, it } from "vitest";

import { runClientTool, type ClientEnv } from "../src/index";
import { checkMode, classifyPayload, isBic, normalizeIban, qrPayload, toSjisBytes, type QrContent } from "../src/qrdata";
import { scanBarcodes } from "../src/qrtools";
import { rgba, type Rgba } from "../src/rasters";
import { parsePathData, parseSvg, svgToPdf } from "../src/svgpdf";
import { renderSvg } from "../src/wasmcodecs";
import { nodeCodec } from "./image-node";
import { nodeRenderer } from "./pdfium-node";
import { nodeWasm, wasmFile } from "./wasm-node";

const FIXTURES = path.join(import.meta.dirname, "fixtures");
const env = (extra: Partial<ClientEnv> = {}): ClientEnv => ({ codec: nodeCodec(), wasm: nodeWasm, renderer: nodeRenderer, ...extra });

/** QR de prueba con qrcode-generator: módulos de `cell` px y zona de silencio de 4 módulos. */
function qrRgba(text: string, cell = 6, ecl: "L" | "M" | "Q" | "H" = "M"): Rgba {
  const qr = qrcode(0, ecl);
  qr.addData(text, "Byte");
  qr.make();
  const n = qr.getModuleCount();
  const size = (n + 8) * cell;
  const img = rgba(size, size);
  img.data.fill(255);
  for (let r = 0; r < n; r += 1) {
    for (let c = 0; c < n; c += 1) {
      if (!qr.isDark(r, c)) continue;
      for (let y = 0; y < cell; y += 1) {
        for (let x = 0; x < cell; x += 1) {
          const i = (((r + 4) * cell + y) * size + (c + 4) * cell + x) * 4;
          img.data[i] = img.data[i + 1] = img.data[i + 2] = 0;
        }
      }
    }
  }
  return img;
}

async function png(img: Rgba): Promise<Uint8Array> {
  await initPng(await WebAssembly.compile(wasmFile("@jsquash/png/codec/pkg/squoosh_png_bg.wasm")));
  return new Uint8Array(await encodePng(img as unknown as ImageData));
}

function qrSvg(text: string): Uint8Array {
  const qr = qrcode(0, "M");
  qr.addData(text, "Byte");
  qr.make();
  return new TextEncoder().encode(qr.createSvgTag({ cellSize: 8, margin: 32, scalable: false }));
}

/** Diferencia media por canal entre dos imágenes del mismo tamaño (0–255). */
function meanDiff(a: Rgba, b: Rgba): number {
  expect([a.width, a.height]).toEqual([b.width, b.height]);
  let sum = 0;
  for (let i = 0; i < a.data.length; i += 4) for (let c = 0; c < 3; c += 1) sum += Math.abs(a.data[i + c] - b.data[i + c]);
  return sum / ((a.data.length / 4) * 3);
}

/** Funde sobre blanco (resvg y PDFium tratan distinto la transparencia del lienzo). */
function onWhite(img: Rgba): Rgba {
  const out = rgba(img.width, img.height);
  for (let i = 0; i < img.data.length; i += 4) {
    const a = img.data[i + 3] / 255;
    for (let c = 0; c < 3; c += 1) out.data[i + c] = img.data[i + c] * a + 255 * (1 - a);
    out.data[i + 3] = 255;
  }
  return out;
}

describe("contenido de generar-codigo-qr (A.1)", () => {
  const base = { tipo: "url" } as QrContent;

  it("URL, texto, WiFi con escapes, teléfono, SMS y correo", () => {
    expect(qrPayload({ ...base, url: "ejemplo.test/ruta" })).toBe("https://ejemplo.test/ruta");
    expect(qrPayload({ ...base, url: "ftp://ejemplo.test" })).toBe("ftp://ejemplo.test");
    expect(qrPayload({ tipo: "texto", texto: "Hola\nmundo" })).toBe("Hola\nmundo");
    expect(qrPayload({ tipo: "wifi", wifi_ssid: 'Casa;"1"', wifi_contrasena: "a:b,c\\d", wifi_cifrado: "WPA", wifi_oculta: true }))
      .toBe('WIFI:T:WPA;S:Casa\\;\\"1\\";P:a\\:b\\,c\\\\d;H:true;;');
    expect(qrPayload({ tipo: "wifi", wifi_ssid: "Libre", wifi_cifrado: "nopass" })).toBe("WIFI:T:nopass;S:Libre;;");
    expect(qrPayload({ tipo: "telefono", telefono_numero: "+34 600 00 00 00" })).toBe("tel:+34600000000");
    expect(qrPayload({ tipo: "sms", sms_numero: "600000000", sms_mensaje: "Hola" })).toBe("SMSTO:600000000:Hola");
    expect(qrPayload({ tipo: "email", email_para: "admin@ejemplo.test", email_asunto: "Hola y adiós", email_mensaje: "¿Qué tal?" }))
      .toBe("mailto:admin@ejemplo.test?subject=Hola%20y%20adi%C3%B3s&body=%C2%BFQu%C3%A9%20tal%3F");
    expect(() => qrPayload({ tipo: "email", email_para: "no-es-correo" })).toThrow("email_invalid");
    expect(() => qrPayload({ tipo: "wifi", wifi_ssid: "Casa", wifi_cifrado: "WPA" })).toThrow("wifi_password_missing");
    expect(() => qrPayload({ tipo: "telefono", telefono_numero: "abc" })).toThrow(expect.objectContaining({ key: "phone_invalid", params: { field: "phone" } }));
  });

  it("vCard 3.0 con el tipo de teléfono y escapes", () => {
    const card = qrPayload({
      tipo: "vcard", vcard_nombre: "Ana", vcard_apellidos: "García López", vcard_empresa: "Producto Demo, S.L.", vcard_cargo: "Dirección",
      vcard_email: "admin@ejemplo.test", vcard_web: "https://ejemplo.test", vcard_telefono: "+34 600 000 000", vcard_tipo_telefono: "movil",
    });
    expect(card.split("\r\n")).toEqual([
      "BEGIN:VCARD", "VERSION:3.0", "N:García López;Ana;;;", "FN:Ana García López", "ORG:Producto Demo\\, S.L.", "TITLE:Dirección",
      "TEL;TYPE=CELL:+34600000000", "EMAIL;TYPE=INTERNET:admin@ejemplo.test", "URL:https://ejemplo.test", "END:VCARD",
    ]);
  });

  it("SEPA (EPC069-12) con IBAN y BIC validados, importe y concepto", () => {
    expect(normalizeIban("es91 2100 0418 4502 0005 1332")).toBe("ES9121000418450200051332");
    expect(normalizeIban("ES9121000418450200051333")).toBeNull();
    expect(normalizeIban("DE8937040044053201300")).toBeNull(); // longitud de Alemania: 22
    expect(isBic("CAIXESBBXXX")).toBe(true);
    expect(isBic("CAIXESB")).toBe(false);
    const epc = qrPayload({ tipo: "sepa", sepa_beneficiario: "Producto Demo", sepa_iban: "ES91 2100 0418 4502 0005 1332", sepa_bic: "caixesbbxxx",
      sepa_importe: 12.5, sepa_concepto: "Factura 2026-001" });
    expect(epc.split("\n")).toEqual(["BCD", "002", "1", "SCT", "CAIXESBBXXX", "Producto Demo", "ES9121000418450200051332", "EUR12.50", "", "", "Factura 2026-001"]);
    expect(qrPayload({ tipo: "sepa", sepa_beneficiario: "Producto Demo", sepa_iban: "ES9121000418450200051332" }).split("\n"))
      .toEqual(["BCD", "002", "1", "SCT", "", "Producto Demo", "ES9121000418450200051332"]);
    expect(() => qrPayload({ tipo: "sepa", sepa_beneficiario: "X", sepa_iban: "ES00" })).toThrow("iban_invalid");
    expect(() => qrPayload({ tipo: "sepa", sepa_beneficiario: "X", sepa_iban: "ES9121000418450200051332", sepa_importe: 1.234 })).toThrow("amount_decimals");
  });

  it("PayPal con correo o PayPal.Me y evento de calendario", () => {
    expect(qrPayload({ tipo: "paypal", paypal_cuenta: "https://paypal.me/ProductoDemo", paypal_importe: 10, paypal_moneda: "eur" }))
      .toBe("https://paypal.me/ProductoDemo/10.00EUR");
    expect(qrPayload({ tipo: "paypal", paypal_cuenta: "admin@ejemplo.test", paypal_importe: 5, paypal_moneda: "USD" }))
      .toBe("https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business=admin%40ejemplo.test&currency_code=USD&amount=5.00");
    const event = qrPayload({ tipo: "evento", evento_titulo: "Reunión; equipo", evento_inicio: "2026-11-04T10:30", evento_fin: "2026-11-04T11:00",
      evento_lugar: "Sala 1", evento_descripcion: "Orden del día" });
    expect(event.split("\r\n")).toEqual(["BEGIN:VEVENT", "SUMMARY:Reunión\\; equipo", "DTSTART:20261104T103000", "DTEND:20261104T110000",
      "LOCATION:Sala 1", "DESCRIPTION:Orden del día", "END:VEVENT"]);
    expect(qrPayload({ tipo: "evento", evento_titulo: "Fiesta", evento_inicio: "2026-12-31", evento_todo_el_dia: true }))
      .toContain("DTSTART;VALUE=DATE:20261231\r\nDTEND;VALUE=DATE:20270101");
    expect(() => qrPayload({ tipo: "evento", evento_titulo: "X", evento_inicio: "2026-11-04T10:00", evento_fin: "2026-11-03T10:00" })).toThrow("event_end_before");
  });

  it("modos numérico, alfanumérico y Kanji (Shift_JIS) y tipo del contenido leído", () => {
    expect(() => checkMode("12345", "numerico")).not.toThrow();
    expect(() => checkMode("12a", "numerico")).toThrow("mode_numeric");
    expect(() => checkMode("HTTPS://EJEMPLO.TEST", "alfanumerico")).not.toThrow();
    expect(() => checkMode("https://ejemplo.test", "alfanumerico")).toThrow("mode_alphanumeric");
    expect(() => checkMode("漢字", "kanji")).not.toThrow();
    expect(() => checkMode("漢a", "kanji")).toThrow(expect.objectContaining({ key: "mode_kanji", params: { ch: "a" } }));
    expect(toSjisBytes("友")).toEqual([0x97, 0x46]);
    expect(classifyPayload("WIFI:T:WPA;S:x;;")).toBe("wifi");
    expect(classifyPayload("BCD\n002\n1\nSCT")).toBe("sepa");
    expect(classifyPayload("https://ejemplo.test")).toBe("enlace");
  });
});

describe("leer-codigo-qr con zxing-cpp", () => {
  it("lee un QR de una imagen PNG y lo exporta a CSV", async () => {
    const res = await runClientTool("leer-codigo-qr", [{ name: "cartel.png", bytes: await png(qrRgba("https://ejemplo.test/hola")) }], { formatos: "qr" }, env());
    expect(res.display).toEqual(["https://ejemplo.test/hola"]);
    expect(res.notes).toEqual(["cartel.png: 1 código (enlace).", "Los enlaces no se abren solos: compruébalos antes de visitarlos."]);
    const csv = new TextDecoder("utf-8", { ignoreBOM: true }).decode(res.outputs[0].bytes);
    expect(csv).toBe("﻿archivo,pagina,formato,contenido\r\ncartel.png,1,QRCode,https://ejemplo.test/hola\r\n");
  });

  it("varios códigos en una imagen, en un PDF (página 2) y ninguno", async () => {
    const a = qrRgba("WIFI:T:WPA;S:Casa;P:clave;;", 5);
    const b = qrRgba("Texto con ñ y tildes: canción", 5);
    const both = rgba(a.width + b.width, Math.max(a.height, b.height));
    both.data.fill(255);
    for (let y = 0; y < both.height; y += 1) {
      if (y < a.height) both.data.set(a.data.subarray(y * a.width * 4, (y + 1) * a.width * 4), y * both.width * 4);
      if (y < b.height) both.data.set(b.data.subarray(y * b.width * 4, (y + 1) * b.width * 4), (y * both.width + a.width) * 4);
    }
    const two = await runClientTool("leer-codigo-qr", [{ name: "dos.png", bytes: await png(both) }], { formatos: "todos" }, env({ locale: "en" }));
    expect([...(two.display ?? [])].sort()).toEqual(["Texto con ñ y tildes: canción", "WIFI:T:WPA;S:Casa;P:clave;;"]);
    expect(two.notes[0]).toMatch(/^dos\.png: 2 codes \((WiFi network, text|text, WiFi network)\)\.$/);

    const doc = await PDFDocument.create();
    doc.addPage([300, 300]);
    const page = doc.addPage([400, 400]);
    const image = await doc.embedPng(await png(qrRgba("Factura 2026-001", 4)));
    page.drawImage(image, { x: 100, y: 100, width: 140, height: 140 });
    const pdf = await runClientTool("leer-codigo-qr", [{ name: "factura.pdf", bytes: await doc.save() }], { formatos: "qr" }, env());
    expect(pdf.display).toEqual(["Factura 2026-001"]);
    expect(new TextDecoder().decode(pdf.outputs[0].bytes)).toContain("factura.pdf,2,QRCode,Factura 2026-001");

    const blank = rgba(50, 50);
    blank.data.fill(255);
    const none = await runClientTool("leer-codigo-qr", [{ name: "nada.png", bytes: await png(blank) }], { formatos: "qr" }, env());
    expect(none).toMatchObject({ outputs: [], display: [], notes: ["nada.png: no se ha encontrado ningún código."] });
  });
});

describe("exportación de generar-codigo-qr", () => {
  it("PNG, SVG y PDF vectorial, comprobados con zxing-cpp", async () => {
    const svg = { name: "codigo.svg", bytes: qrSvg("https://ejemplo.test/qr") };
    const opts = { contenido: "https://ejemplo.test/qr", nombre: "mi-qr" };
    const asPng = await runClientTool("generar-codigo-qr", [svg], { ...opts, formato: "png" }, env());
    expect(asPng.outputs.map((o) => [o.name, o.note])).toEqual([["mi-qr.png", "QR_OK"]]);
    expect(asPng.notes).toEqual(["Comprobado: el código se lee correctamente."]);
    const asSvg = await runClientTool("generar-codigo-qr", [svg], { ...opts, formato: "svg" }, env());
    expect(asSvg.outputs.map((o) => [o.name, o.mime, o.note])).toEqual([["mi-qr.svg", "image/svg+xml", "QR_OK"], ["mi-qr.png", "image/png", "clipboard"]]);
    const asPdf = await runClientTool("generar-codigo-qr", [svg], { ...opts, formato: "pdf" }, env({ locale: "en" }));
    expect(asPdf.outputs[0]).toMatchObject({ name: "mi-qr.pdf", note: "QR_OK" });
    const doc = await nodeRenderer.open(asPdf.outputs[0].bytes);
    const raster = await doc.render(0, 2);
    doc.close();
    expect((await scanBarcodes(nodeWasm, raster, { formats: ["QRCode"] }))[0]?.text).toBe("https://ejemplo.test/qr");
    // Vectorial: sin imágenes dentro del PDF.
    const parsed = await PDFDocument.load(asPdf.outputs[0].bytes);
    const images = [...parsed.context.enumerateIndirectObjects()].filter(([, o]) => o instanceof PDFRawStream && o.dict.get(PDFName.of("Subtype"))?.toString() === "/Image");
    expect(images).toHaveLength(0);
  });

  it("avisa si el código no se lee o se lee con otro contenido", async () => {
    const empty = new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#fff"/></svg>');
    const res = await runClientTool("generar-codigo-qr", [{ name: "x.svg", bytes: empty }], { formato: "png", contenido: "hola" }, env());
    expect(res.outputs[0].note).toBe("QR_UNREADABLE");
    expect(res.notes[0]).toMatch(/^No se ha podido leer el código generado/);
    const other = await runClientTool("generar-codigo-qr", [{ name: "x.svg", bytes: qrSvg("otro") }], { formato: "png", contenido: "hola" }, env());
    expect(other.notes[0]).toMatch(/otro contenido/);
  });
});

describe("SVG → PDF vectorial", () => {
  it("interpreta trazados con arcos y órdenes relativas", () => {
    const segs = parsePathData("M 10 10 h 5 v 5 a 2 2 0 0 1 -2 2 Z m 1 1 l 1 1");
    expect(segs[0]).toEqual(["M", 10, 10]);
    expect(segs[1]).toEqual(["L", 15, 10]);
    expect(segs[2]).toEqual(["L", 15, 15]);
    const arcEnd = segs[3] as number[];
    expect(arcEnd[0]).toBe("C");
    expect(arcEnd.slice(5)).toEqual([13, 17]);
    expect(segs[4]).toEqual(["Z"]);
    expect(segs[5]).toEqual(["M", 11, 11]);
    expect(parseSvg('<?xml version="1.0"?><svg width="1" height="1"><rect a="&lt;b&amp;"/></svg>').children[0].attrs.a).toBe("<b&");
  });

  for (const name of ["qr-styled", "qr-logo", "qr-circle"]) {
    it(`${name}.svg de qr-code-styling: el PDF se ve como el SVG y se lee`, async () => {
      const svg = readFileSync(path.join(FIXTURES, `${name}.svg`));
      const { bytes, warnings } = await svgToPdf(svg.toString("utf-8"));
      expect(warnings).toEqual([]);
      const doc = await nodeRenderer.open(bytes);
      // 300 px CSS = 225 pt; a escala 4/3 el PDF se pinta a 300 × 300 píxeles, como el SVG.
      const fromPdf = await doc.render(0, 4 / 3);
      doc.close();
      const fromSvg = (await renderSvg(nodeWasm, new Uint8Array(svg), { mode: "original" })).pixels;
      expect(meanDiff(onWhite(fromPdf), onWhite(fromSvg))).toBeLessThan(4);
      // La forma circular con puntos es decorativa y zxing no siempre la lee: para eso está el aviso de la herramienta.
      if (name !== "qr-circle") {
        expect((await scanBarcodes(nodeWasm, onWhite(fromPdf), { formats: ["QRCode"], tryHarder: true }))[0]?.text).toBe("https://ejemplo.test/qr");
      }
    });
  }
});
