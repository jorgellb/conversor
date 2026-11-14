import { PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, PDFNumber, PDFRawStream, PDFString, StandardFonts, degrees, rgb } from "@cantoo/pdf-lib";
import { unzlibSync } from "fflate";
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
    await expect(runClientTool("redactar-pdf", [{ name: "x.pdf", bytes }], { color: "#000000", texto: "", metodo: "borrar", model: { areas: [{ page: 0, x: 1, y: 1, width: 5, height: 5 }] } },
      { renderer: nodeRenderer })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });
});

/** Todo el contenido del archivo (con los flujos descomprimidos) en latin1, para buscar restos del texto redactado. */
function rawText(bytes: Uint8Array, doc: PDFDocument): string {
  const parts = [new TextDecoder("latin1").decode(bytes)];
  for (const [, obj] of doc.context.enumerateIndirectObjects()) {
    if (!(obj instanceof PDFRawStream)) continue;
    try {
      parts.push(new TextDecoder("latin1").decode(obj.dict.get(PDFName.of("Filter")) ? unzlibSync(obj.contents) : obj.contents));
    } catch {
      parts.push(new TextDecoder("latin1").decode(obj.contents));
    }
  }
  return parts.join("\n");
}

/** El texto buscado en claro o como cadena hexadecimal (como lo escribe pdf-lib con las fuentes estándar). */
function leaks(raw: string, text: string): boolean {
  const hex = Array.from(new TextEncoder().encode(text)).map((b) => b.toString(16).padStart(2, "0")).join("");
  return raw.includes(text) || raw.toLowerCase().includes(hex);
}

/** Quita el último flujo de contenido (los recuadros que añade pdf-lib) para ver lo que hay debajo. */
async function withoutBoxes(bytes: Uint8Array): Promise<Uint8Array> {
  const doc = await PDFDocument.load(bytes);
  const page = doc.getPages()[0];
  const contents = page.node.lookup(PDFName.of("Contents"), PDFArray);
  contents.remove(contents.size() - 1);
  return doc.save();
}

async function whiteInside(bytes: Uint8Array, area: Area, page = 0): Promise<boolean> {
  const doc = await nodeRenderer.open(bytes);
  try {
    const img = await doc.render(page, 1);
    for (let y = Math.ceil(area.y + 2); y < area.y + area.height - 2; y += 1) {
      for (let x = Math.ceil(area.x + 2); x < area.x + area.width - 2; x += 1) {
        const p = (y * img.width + x) * 4;
        if (img.data[p] < 250 || img.data[p + 1] < 250 || img.data[p + 2] < 250) return false;
      }
    }
    return true;
  } finally {
    doc.close();
  }
}

describe("redactar-pdf eliminando solo lo que hay bajo el área (A.6, 16.4 y 16.6; D-153)", () => {
  it("quita el texto, los píxeles de la imagen y el trazado bajo las áreas y conserva el resto del texto", async () => {
    const original = await samplePdf();
    const pages = await pagesText(original);
    const areas: Area[] = [...findMatches(pages, "Juan Pérez"), ...findPattern(pages, "dni")].flatMap((m) => m.areas);
    // Área que cubre parte de la imagen y de la línea azul (de 30,300 a 300,340 desde abajo).
    const extra = { page: 0, x: 40, y: 50, width: 60, height: 40 };
    areas.push(extra);
    const res = await runClientTool("redactar-pdf", [{ name: "exp.pdf", bytes: original }], {
      color: "#000000", texto: "", metodo: "eliminar", model: { areas, terminos: ["Juan Pérez", "12345678Z"] },
    }, { renderer: nodeRenderer, locale: "en" });
    const out = res.outputs[0].bytes;
    expect(res.outputs[0].name).toBe("exp-redactado.pdf");
    const text = await pagesText(out);
    const page1 = text[0].chars.map((c) => c.ch).join("");
    expect(page1).not.toContain("Juan");
    expect(page1).not.toContain("12345678Z");
    // A diferencia de «rasterizar», el resto del texto de la página sigue siendo texto.
    expect(page1).toContain("García");
    expect(page1).toContain("ES91 2100");
    expect(page1).toContain("juan.perez@ejemplo.test");
    expect(text[1].chars.map((c) => c.ch).join("")).toContain("Anexo sin datos personales");
    // Ni rastro en el archivo (flujos huérfanos incluidos).
    const pdf = await PDFDocument.load(out);
    const raw = rawText(out, pdf);
    for (const secret of ["Juan P", "12345678Z"]) expect(leaks(raw, secret)).toBe(false);
    // Los recuadros tapan las áreas...
    const doc = await nodeRenderer.open(out);
    const img = await doc.render(0, 1);
    doc.close();
    for (const [x, y] of [[45, 55], [95, 85], [70, 70]]) {
      const p = (y * img.width + x) * 4;
      expect(img.data[p] + img.data[p + 1] + img.data[p + 2]).toBeLessThan(40);
    }
    // ...y debajo ya no se dibuja nada: ni la imagen ni el trazado (sin los recuadros, el área queda en blanco).
    const bare = await withoutBoxes(out);
    expect(await whiteInside(bare, extra)).toBe(true);
    // Fuera del área, la imagen y la línea siguen ahí.
    const view = await nodeRenderer.open(bare);
    const around = await view.render(0, 1);
    view.close();
    const at = (x: number, y: number) => Array.from(around.data.slice((y * 400 + x) * 4, (y * 400 + x) * 4 + 3));
    expect(at(140, 70)).not.toEqual([255, 255, 255]); // imagen a la derecha del área
    // La imagen original de 30 × 30 ya no está en el archivo.
    const originals = [...pdf.context.enumerateIndirectObjects()].filter(([, o]) => o instanceof PDFRawStream
      && o.dict.get(PDFName.of("Subtype")) === PDFName.of("Image") && (o.dict.get(PDFName.of("Width")) as PDFNumber)?.asNumber() === 30);
    expect(originals).toHaveLength(0);
    expect(pdf.getTitle()).toBeUndefined();
    expect(res.notes.join(" ")).toMatch(/can still be selected/);
  });

  it("respeta el giro de la página y quita los enlaces y campos que tocan un área", async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const page = doc.addPage([300, 400]);
    page.setRotation(degrees(90));
    page.drawText("Cuenta secreta 998877", { x: 40, y: 300, size: 12, font });
    page.drawText("Texto que se queda", { x: 40, y: 100, size: 12, font });
    const form = doc.getForm();
    const field = form.createTextField("dni");
    field.setText("12345678Z");
    field.addToPage(page, { x: 40, y: 270, width: 120, height: 20 });
    const link = doc.context.obj({ Type: "Annot", Subtype: "Link", Rect: [40, 295, 200, 315], A: { S: "URI", URI: PDFString.of("https://example.com/") } });
    page.node.addAnnot(doc.context.register(link));
    const bytes = await doc.save();
    const pages = await pagesText(bytes);
    const areas = [...findMatches(pages, "Cuenta secreta 998877")].flatMap((m) => m.areas);
    // En la página vista (girada 90°), el área del texto queda en vertical a la derecha.
    // En la página vista (girada 90°), el texto va en vertical: x ≈ 299 y de y = 40 hacia abajo.
    expect(areas.every((a) => a.x > 290 && a.x < 310)).toBe(true);
    // El campo (de y = 270 a 290 en la página) queda al lado, en la franja x = 270-290 de la vista.
    areas.push({ page: 0, x: 266, y: 35, width: 28, height: 130 });
    const res = await runClientTool("redactar-pdf", [{ name: "girada.pdf", bytes }], {
      color: "#000000", texto: "OCULTO", metodo: "eliminar", model: { areas, terminos: ["998877"] },
    }, { renderer: nodeRenderer });
    const out = res.outputs[0].bytes;
    const text = (await pagesText(out))[0].chars.map((c) => c.ch).join("");
    expect(text).not.toContain("998877");
    expect(text).toContain("Texto que se queda");
    const pdf = await PDFDocument.load(out);
    expect(pdf.getPages()[0].getRotation().angle).toBe(90);
    expect(pdf.getPages()[0].node.Annots()?.size() ?? 0).toBe(0);
    expect(pdf.getForm().getFields()).toHaveLength(0);
    expect(leaks(rawText(out, pdf), "12345678Z")).toBe(false);
    expect(res.notes.join(" ")).toMatch(/anotación/);
  });

  it("también borra lo que hay dentro de un grupo (Form XObject) y una página escaneada (imagen a página completa)", async () => {
    const inner = await PDFDocument.create();
    const font = await inner.embedFont(StandardFonts.Helvetica);
    const p = inner.addPage([400, 400]);
    p.drawText("Dato secreto 4455", { x: 50, y: 300, size: 14, font });
    p.drawText("Dato publico", { x: 50, y: 200, size: 14, font });
    const doc = await PDFDocument.create();
    const [embedded] = await doc.embedPdf(await inner.save());
    doc.addPage([400, 400]).drawPage(embedded);
    const scan = doc.addPage([400, 400]);
    scan.drawImage(await doc.embedPng(b64(PNG_30x30)), { x: 0, y: 0, width: 400, height: 400 });
    const bytes = await doc.save();
    const areas: Area[] = [
      ...findMatches(await pagesText(bytes), "secreto 4455").flatMap((m) => m.areas),
      { page: 1, x: 100, y: 100, width: 80, height: 50 },
    ];
    const res = await runClientTool("redactar-pdf", [{ name: "grupo.pdf", bytes }], {
      color: "#000000", texto: "", metodo: "eliminar", model: { areas, terminos: ["4455"] },
    }, { renderer: nodeRenderer });
    const out = res.outputs[0].bytes;
    const text = await pagesText(out);
    expect(text[0].chars.map((c) => c.ch).join("")).not.toContain("4455");
    const pdf = await PDFDocument.load(out);
    expect(leaks(rawText(out, pdf), "4455")).toBe(false);
    expect(res.notes.join(" ")).toMatch(/convertido en imagen/);
    // El texto del grupo que queda fuera del área («Dato publico») ha pasado a imagen con él: el aviso lo dice y no
    // promete que siga seleccionable en esa página.
    expect(text[0].chars.map((c) => c.ch).join("")).not.toContain("publico");
    expect(res.notes.some((n) => n.startsWith("Páginas 1:") && /ya no se puede seleccionar/.test(n))).toBe(true);
    expect(res.notes.some((n) => /sigue siendo seleccionable/.test(n) && /páginas 1(,|;|$)/.test(n))).toBe(false);
    expect(res.notes.join(" ")).toMatch(/páginas 2; el resto del texto sigue siendo seleccionable/);
  });

  for (const metodo of ["eliminar", "rasterizar"] as const) {
    it(`«${metodo}» no deja el texto en las etiquetas, la capa XFA ni las cadenas del archivo`, async () => {
      const doc = await PDFDocument.create();
      const font = await doc.embedFont(StandardFonts.Helvetica);
      const page = doc.addPage([400, 400]);
      page.drawText("Secreto 776655", { x: 50, y: 300, size: 14, font });
      page.drawText("Texto que se queda", { x: 50, y: 100, size: 14, font });
      const ctx = doc.context;
      const utf16 = (text: string) => PDFHexString.fromText(text);
      // Estructura de etiquetas con el texto repetido en /ActualText, /Alt, /E y /T.
      const elem = ctx.register(ctx.obj({ Type: "StructElem", S: "P", ActualText: utf16("Secreto 776655"), Alt: utf16("Secreto 776655"),
        E: utf16("776655"), T: PDFString.of("Cuenta 776655") }));
      doc.catalog.set(PDFName.of("StructTreeRoot"), ctx.register(ctx.obj({ Type: "StructTreeRoot", K: [elem] })));
      doc.catalog.set(PDFName.of("MarkInfo"), ctx.obj({ Marked: true }));
      page.node.set(PDFName.of("StructParents"), PDFNumber.of(0));
      // Capa XFA con el valor de un campo.
      const xfa = ctx.register(ctx.flateStream("<xdp:xdp><xfa:datasets><cuenta>776655</cuenta></xfa:datasets></xdp:xdp>"));
      doc.catalog.set(PDFName.of("AcroForm"), ctx.obj({ Fields: [], XFA: [PDFString.of("datasets"), xfa] }));
      // Un enlace fuera del área con el término en la URL.
      const link = ctx.obj({ Type: "Annot", Subtype: "Link", Rect: [50, 90, 200, 120], A: { S: "URI", URI: PDFString.of("https://example.com/?c=776655") } });
      page.node.addAnnot(ctx.register(link));
      const bytes = await doc.save();
      const areas = findMatches(await pagesText(bytes), "776655").flatMap((m) => m.areas);
      const res = await runClientTool("redactar-pdf", [{ name: "etiquetado.pdf", bytes }], {
        color: "#000000", texto: "", metodo, model: { areas, terminos: ["776655"] },
      }, { renderer: nodeRenderer });
      const out = res.outputs[0].bytes;
      const pdf = await PDFDocument.load(out);
      const raw = rawText(out, pdf);
      expect(leaks(raw, "776655")).toBe(false);
      // UTF-16BE (como se guardan /ActualText y /Alt).
      const utf16hex = Array.from("776655").map((c) => c.charCodeAt(0).toString(16).padStart(4, "0")).join("");
      expect(raw.toLowerCase()).not.toContain(utf16hex);
      expect(pdf.catalog.get(PDFName.of("StructTreeRoot"))).toBeUndefined();
      expect(pdf.catalog.lookup(PDFName.of("AcroForm"), PDFDict).get(PDFName.of("XFA"))).toBeUndefined();
      expect(res.notes.join(" ")).toMatch(/etiquetas de accesibilidad/);
      // El enlace de fuera del área sigue (con «eliminar»; «rasterizar» quita las anotaciones de la página) y tapado.
      if (metodo === "eliminar") expect(res.notes.join(" ")).toMatch(/en 1 texto\(s\) del archivo/);
    });
  }

  it("la comprobación final falla si el término sigue en una cadena del flujo de contenido (/ActualText en línea)", async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const page = doc.addPage([400, 400]);
    page.drawText("Clave 5566", { x: 50, y: 300, size: 14, font });
    page.drawText("Otro texto", { x: 50, y: 100, size: 14, font });
    // Un contenido marcado lejos del área con el término como /ActualText de un trazado (no es texto de la página).
    const extra = doc.context.flateStream("/Span <</ActualText (Clave 5566)>> BDC 300 20 5 5 re f EMC\n");
    page.node.normalizedEntries().Contents!.push(doc.context.register(extra));
    const bytes = await doc.save();
    const areas = findMatches(await pagesText(bytes), "5566").flatMap((m) => m.areas);
    for (const metodo of ["eliminar", "rasterizar"] as const) {
      const run = runClientTool("redactar-pdf", [{ name: "marcado.pdf", bytes }], {
        color: "#000000", texto: "", metodo, model: { areas, terminos: ["5566"] },
      }, { renderer: nodeRenderer });
      if (metodo === "rasterizar") {
        // La página entera pasa a imagen: el flujo con el contenido marcado desaparece.
        const out = (await run).outputs[0].bytes;
        expect(leaks(rawText(out, await PDFDocument.load(out)), "5566")).toBe(false);
      } else {
        // PDFium regenera el contenido y conserva el contenido marcado: la comprobación de todo el archivo lo
        // encuentra y no se entrega nada (mejor un error que un archivo con el dato).
        await expect(run).rejects.toMatchObject({ code: "REDACTION_FAILED", message: expect.stringMatching(/dentro del archivo/) });
      }
    }
  });

  it("fuera de las áreas la página se ve igual, con los objetos superpuestos en su orden", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([400, 400]);
    page.drawRectangle({ x: 50, y: 100, width: 100, height: 100, color: rgb(0, 0, 1) });
    page.drawRectangle({ x: 100, y: 100, width: 100, height: 100, color: rgb(1, 0, 0), opacity: 0.5 });
    page.drawImage(await doc.embedPng(b64(PNG_30x30)), { x: 120, y: 150, width: 120, height: 60 });
    const bytes = await doc.save();
    const area: Area = { page: 0, x: 90, y: 220, width: 70, height: 40 };
    const res = await runClientTool("redactar-pdf", [{ name: "capas.pdf", bytes }], {
      color: "#000000", texto: "", metodo: "eliminar", model: { areas: [area] },
    }, { renderer: nodeRenderer });
    const render = async (b: Uint8Array) => {
      const d = await nodeRenderer.open(b);
      try {
        return await d.render(0, 1);
      } finally {
        d.close();
      }
    };
    const before = await render(bytes);
    const after = await render(await withoutBoxes(res.outputs[0].bytes));
    let differ = 0;
    for (let y = 0; y < 400; y += 1) {
      for (let x = 0; x < 400; x += 1) {
        const near = x > area.x - 3 && x < area.x + area.width + 3 && y > area.y - 3 && y < area.y + area.height + 3;
        if (near) continue;
        const p = (y * 400 + x) * 4;
        if (Math.abs(before.data[p] - after.data[p]) + Math.abs(before.data[p + 1] - after.data[p + 1]) + Math.abs(before.data[p + 2] - after.data[p + 2]) > 30) differ += 1;
      }
    }
    // Solo varía el suavizado de los bordes de los objetos convertidos en imagen (líneas de un píxel).
    expect(differ).toBeLessThan(1000);
    const at = (img: { data: Uint8ClampedArray }, x: number, y: number) => Array.from(img.data.slice((y * 400 + x) * 4, (y * 400 + x) * 4 + 3));
    // Azul solo, azul bajo el rojo semitransparente, rojo solo e imagen encima: igual que antes.
    for (const [x, y] of [[60, 250], [125, 280], [180, 280], [220, 200], [130, 205]]) expect(at(after, x, y)).toEqual(at(before, x, y));
    expect(await whiteInside(await withoutBoxes(res.outputs[0].bytes), area)).toBe(true);
  });

  it("«rasterizar» tampoco deja el contenido sustituido dentro del archivo", async () => {
    const original = await samplePdf();
    const areas = findMatches(await pagesText(original), "Juan Pérez").flatMap((m) => m.areas);
    const res = await runClientTool("redactar-pdf", [{ name: "x.pdf", bytes: original }], {
      color: "#000000", texto: "", metodo: "rasterizar", model: { areas, terminos: ["Juan Pérez"] },
    }, { renderer: nodeRenderer });
    const out = res.outputs[0].bytes;
    expect(leaks(rawText(out, await PDFDocument.load(out)), "Juan P")).toBe(false);
  });
});

describe("cadenas de un flujo de contenido (comprobación de redactar-pdf)", () => {
  it("lee literales con escapes y paréntesis, hexadecimales y salta comentarios, diccionarios e imágenes en línea", async () => {
    const { contentStrings } = await import("../src/redact");
    const bytes = new TextEncoder().encode(
      "% (comentario)\nBT (a\\(b\\) \\101 (c)) Tj <48 6f6C61> Tj <</ActualText <FEFF0041>>> BDC ET\n"
      + "BI /W 1 /H 1 /BPC 8 /CS /G ID (x) EI\nre f",
    );
    const parts = contentStrings(bytes).map((b) => Array.from(b));
    expect(parts).toEqual([
      Array.from(new TextEncoder().encode("a(b) A (c)")),
      [0x48, 0x6f, 0x6c, 0x61],
      [0xfe, 0xff, 0x00, 0x41],
    ]);
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
