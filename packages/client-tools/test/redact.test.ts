import { PDFDict, PDFDocument, PDFHexString, PDFName, StandardFonts, rgb } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { addOutline } from "../src/pdfutil";
import { findMatches, findPattern, runClientTool, type Area } from "../src/index";
import { PNG_30x30, b64 } from "./images.fixture";
import { nodeRenderer } from "./pdfium-node";

/** Página 1: nombre y DNI, una imagen bajo parte del área y una línea que la cruza. Página 2: texto que no se toca. */
async function samplePdf(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  doc.setTitle("Expediente de Juan Pérez");
  doc.setAuthor("Oficina");
  const p1 = doc.addPage([400, 400]);
  const image = await doc.embedPng(b64(PNG_30x30));
  p1.drawImage(image, { x: 40, y: 290, width: 120, height: 60 });
  p1.drawText("Juan Pérez García", { x: 50, y: 320, size: 14, font });
  p1.drawText("DNI 12345678Z  ES91 2100 0418 4502 0005 1332", { x: 50, y: 250, size: 10, font });
  p1.drawText("correo: juan.perez@ejemplo.test tel. 612 345 678", { x: 50, y: 220, size: 10, font });
  p1.drawLine({ start: { x: 30, y: 300 }, end: { x: 300, y: 340 }, thickness: 3, color: rgb(0, 0, 1) });
  const p2 = doc.addPage([400, 400]);
  p2.drawText("Anexo sin datos personales", { x: 50, y: 300, size: 12, font });
  addOutline(doc, [{ title: "Datos de Juan Pérez", pageIndex: 0 }, { title: "Anexo", pageIndex: 1 }]);
  return doc.save();
}

async function pagesText(bytes: Uint8Array) {
  const doc = await nodeRenderer.open(bytes);
  try {
    return Array.from({ length: doc.pageCount }, (_, i) => ({ page: i, chars: doc.text(i) }));
  } finally {
    doc.close();
  }
}

describe("búsqueda y patrones para redactar (A.6)", () => {
  it("encuentra el texto sin distinguir mayúsculas ni tildes, con su caja en la página vista", async () => {
    const pages = await pagesText(await samplePdf());
    const [match] = findMatches(pages, "juan perez");
    expect(match.page).toBe(0);
    expect(match.text).toBe("Juan Pérez");
    const area = match.areas[0];
    // La línea base está en y = 320 desde abajo → unos 66-80 pt desde arriba en una página de 400.
    expect(area.y).toBeGreaterThan(60);
    expect(area.y + area.height).toBeLessThan(90);
    expect(area.x).toBeGreaterThan(45);
  });

  it("patrones de DNI, IBAN, correo y teléfono", async () => {
    const pages = await pagesText(await samplePdf());
    expect(findPattern(pages, "dni").map((m) => m.text)).toEqual(["12345678Z"]);
    expect(findPattern(pages, "iban")[0].text.replace(/\s/g, "")).toBe("ES9121000418450200051332");
    expect(findPattern(pages, "email").map((m) => m.text)).toEqual(["juan.perez@ejemplo.test"]);
    expect(findPattern(pages, "telefono").map((m) => m.text.trim())).toEqual(["612 345 678"]);
  });
});

describe("redactar-pdf rasterizando (16.4 y 16.6)", () => {
  it("no queda el texto, los píxeles de la imagen y el trazado quedan tapados y el resto sigue intacto", async () => {
    const original = await samplePdf();
    const pages = await pagesText(original);
    const areas: Area[] = [...findMatches(pages, "Juan Pérez"), ...findPattern(pages, "dni")].flatMap((m) => m.areas);
    // Área extra que cubre parte de la imagen y de la línea azul.
    areas.push({ page: 0, x: 40, y: 50, width: 60, height: 40 });
    const res = await runClientTool("redactar-pdf", [{ name: "exp.pdf", bytes: original }], {
      color: "#000000", texto: "", metodo: "rasterizar", model: { areas, terminos: ["Juan Pérez", "12345678Z"] },
    }, { renderer: nodeRenderer });
    const out = res.outputs[0].bytes;
    const text = await pagesText(out);
    const page1 = text[0].chars.map((c) => c.ch).join("");
    expect(page1).not.toContain("Juan");
    expect(page1).not.toContain("12345678Z");
    // La página afectada es ahora una imagen: no queda texto; la otra conserva el suyo.
    expect(page1.trim()).toBe("");
    expect(text[1].chars.map((c) => c.ch).join("")).toContain("Anexo sin datos personales");
    // Píxeles del área extra (imagen y trazado) sustituidos por negro.
    const doc = await nodeRenderer.open(out);
    const img = await doc.render(0, 1);
    doc.close();
    for (const [x, y] of [[45, 55], [95, 85], [70, 70]]) {
      const p = (y * img.width + x) * 4;
      expect(img.data[p] + img.data[p + 1] + img.data[p + 2]).toBeLessThan(40);
    }
    // Metadatos fuera y marcador tapado.
    const pdf = await PDFDocument.load(out);
    expect(pdf.getTitle()).toBeUndefined();
    expect(pdf.getAuthor()).toBeUndefined();
    const first = pdf.catalog.lookup(PDFName.of("Outlines"), PDFDict).lookup(PDFName.of("First"), PDFDict);
    expect((first.lookup(PDFName.of("Title")) as PDFHexString).decodeText()).not.toContain("Pérez");
    expect(res.notes.join(" ")).toMatch(/OCR/);
  });

  it("pone el texto en el recuadro y lo admite en la comprobación", async () => {
    const original = await samplePdf();
    const areas = findMatches(await pagesText(original), "Juan Pérez García").flatMap((m) => m.areas);
    const res = await runClientTool("redactar-pdf", [{ name: "x.pdf", bytes: original }], {
      color: "#000000", texto: "OCULTO", metodo: "rasterizar", model: { areas, terminos: ["Juan Pérez García"] },
    }, { renderer: nodeRenderer });
    const text = (await pagesText(res.outputs[0].bytes))[0].chars.map((c) => c.ch).join("");
    expect(text).toContain("OCULTO");
    expect(text).not.toContain("Juan");
  });

  it("sin áreas o con un método no disponible, falla", async () => {
    const bytes = await samplePdf();
    await expect(runClientTool("redactar-pdf", [{ name: "x.pdf", bytes }], { color: "#000000", texto: "", metodo: "rasterizar", model: { areas: [] } },
      { renderer: nodeRenderer })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(runClientTool("redactar-pdf", [{ name: "x.pdf", bytes }], { color: "#000000", texto: "", metodo: "eliminar", model: { areas: [{ page: 0, x: 1, y: 1, width: 5, height: 5 }] } },
      { renderer: nodeRenderer })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });
});

describe("patrón de teléfono", () => {
  it("encuentra teléfonos y no confunde DNI ni grupos de IBAN", async () => {
    const { PATTERNS } = await import("../src/textsearch");
    const found = (t: string) => [...t.matchAll(PATTERNS.telefono)].map((m) => m[0]);
    expect(found("tel. 612 345 678 y 912345678")).toEqual(["612 345 678", "912345678"]);
    expect(found("llama al +34 612 345 678 o al 91 234 56 78")).toEqual(["+34 612 345 678", "91 234 56 78"]);
    expect(found("DNI 12345678Z IBAN ES91 2100 0418 4502 0005 1332")).toEqual([]);
    expect(found("ES76 2077 0024 0031 0257 5766")).toEqual([]);
  });
});
