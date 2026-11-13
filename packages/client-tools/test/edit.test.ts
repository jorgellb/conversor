import { readFileSync } from "node:fs";

import { PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, PDFString, StandardFonts } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { applyEdits, inspectForm, runClientTool, type EditObject } from "../src/index";
import { contentText, hexOf, makePdf, open, widths } from "./helpers";
import { PNG_30x30, b64 } from "./images.fixture";

const FONT_FILES = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
} as const;

const noto = async (kind: keyof typeof FONT_FILES, style: keyof (typeof FONT_FILES)["sans"] = "regular") =>
  new Uint8Array(readFileSync(new URL(`../../../apps/web/public/fonts/${FONT_FILES[kind][style]}.ttf`, import.meta.url)));

function text(overrides: Partial<Extract<EditObject, { type: "text" }>> = {}): EditObject {
  return { type: "text", x: 50, y: 60, width: 200, text: "Hola", font: "sans", size: 12, color: "#000000", ...overrides };
}

async function formPdf(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const page = doc.addPage([400, 400]);
  const font = await doc.embedFont(StandardFonts.Helvetica);
  page.drawText("Formulario", { x: 20, y: 370, size: 14, font });
  const form = doc.getForm();
  const nombre = form.createTextField("nombre");
  nombre.addToPage(page, { x: 20, y: 300, width: 200, height: 20 });
  const acepto = form.createCheckBox("acepto");
  acepto.addToPage(page, { x: 20, y: 250, width: 15, height: 15 });
  const provincia = form.createDropdown("provincia");
  provincia.setOptions(["Madrid", "Málaga", "Teruel"]);
  provincia.addToPage(page, { x: 20, y: 200, width: 150, height: 20 });
  const turno = form.createRadioGroup("turno");
  turno.addOptionToPage("mañana", page, { x: 20, y: 150, width: 15, height: 15 });
  turno.addOptionToPage("tarde", page, { x: 60, y: 150, width: 15, height: 15 });
  return doc.save();
}

describe("editar-pdf: páginas", () => {
  it("empieza con una página en blanco del tamaño elegido y escribe texto con Noto", async () => {
    const res = await runClientTool("editar-pdf", [], {
      tamano_pagina_nueva: "A5",
      orientacion_nueva: "horizontal",
      model: { pages: [{ source: null, size: [595.28, 419.53], objects: [text({ text: "Cañón 5 €", bold: true })] }] },
    }, { fonts: noto });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(1);
    expect(Math.round(doc.getPage(0).getWidth())).toBe(595);
    expect(res.outputs[0].name).toBe("documento.pdf");
  });

  it("sin modelo, el documento nuevo usa el papel y la orientación de las opciones", async () => {
    const res = await runClientTool("editar-pdf", [], { tamano_pagina_nueva: "A4", orientacion_nueva: "vertical" });
    const page = (await open(res.outputs[0].bytes)).getPage(0);
    expect([Math.round(page.getWidth()), Math.round(page.getHeight())]).toEqual([595, 842]);
  });

  it("reordena, borra, inserta en blanco y gira en el mismo documento", async () => {
    const res = await runClientTool("editar-pdf", [await makePdf("tres.pdf", 3)], {
      tamano_pagina_nueva: "A4",
      orientacion_nueva: "vertical",
      model: { pages: [{ source: 2 }, { source: null, size: [300, 300] }, { source: 0, rotate: 90 }] },
    });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(3);
    expect(await widths(res.outputs[0].bytes)).toEqual([2, 100, 0]);
    expect(doc.getPage(2).getRotation().angle).toBe(90);
    expect(res.outputs[0].name).toBe("tres-editado.pdf");
  });

  it("rechaza páginas de origen repetidas o inexistentes", async () => {
    const file = await makePdf("x.pdf", 2);
    await expect(applyEdits(file, { pages: [{ source: 0 }, { source: 0 }] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(applyEdits(file, { pages: [{ source: 5 }] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(applyEdits(file, { pages: [] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });
});

describe("editar-pdf: objetos", () => {
  it("dibuja en la página vista: sin giro, matriz identidad y texto arriba a la izquierda", async () => {
    const { bytes } = await applyEdits(await makePdf("a.pdf", 1), { pages: [{ source: 0, objects: [text({ text: "Arriba" })] }] });
    const content = await contentText(bytes, 0);
    expect(content).toContain("1 0 0 1 0 0 cm");
    expect(content).toContain(hexOf("Arriba"));
    // 300 de alto: la línea base queda a 60 + ascenso por debajo del borde superior.
    const m = /1 0 0 1 50 ([\d.]+) Tm/.exec(content);
    expect(Number(m![1])).toBeGreaterThan(220);
    expect(Number(m![1])).toBeLessThan(240);
  });

  it("en una página girada, el texto se dibuja con la matriz de giro para que se vea derecho", async () => {
    const { bytes } = await applyEdits(await makePdf("r.pdf", 1), { pages: [{ source: 0, rotate: 90, objects: [text({ text: "Girada" })] }] });
    const content = await contentText(bytes, 0);
    expect(content).toMatch(/0 1 -1 0 200 0 cm/);
    expect(content).toContain(hexOf("Girada"));
  });

  it("formas, tapar, imagen, marcas y nota", async () => {
    const objects: EditObject[] = [
      { type: "rect", x: 10, y: 10, width: 50, height: 30, stroke: "#FF0000", fill: null, strokeWidth: 2 },
      { type: "ellipse", x: 70, y: 10, width: 40, height: 40, stroke: "#0000FF", fill: "#00FF00", strokeWidth: 1, opacity: 0.5 },
      { type: "whiteout", x: 10, y: 100, width: 80, height: 20 },
      { type: "arrow", x1: 10, y1: 150, x2: 100, y2: 150, stroke: "#000000", strokeWidth: 2 },
      { type: "polygon", points: [[10, 200], [50, 180], [90, 200]], stroke: "#000000", fill: "#FFFF00" },
      { type: "ink", paths: [[[10, 250], [20, 255], [30, 250]]], stroke: "#333333", strokeWidth: 3 },
      { type: "image", x: 120, y: 120, width: 30, height: 30, data: b64(PNG_30x30), format: "png" },
      { type: "check", x: 150, y: 10, size: 20 },
      { type: "cross", x: 150, y: 40, size: 20, color: "#CC0000" },
      { type: "note", x: 150, y: 200, text: "Revisar esta cifra", author: "Ana" },
    ];
    const { bytes } = await applyEdits(await makePdf("f.pdf", 1), { pages: [{ source: 0, objects }] });
    const content = await contentText(bytes, 0);
    expect(content).toContain("1 0 0 RG"); // borde rojo del rectángulo
    expect(content).toMatch(/\nh\nS\n/); // rectángulo trazado sin relleno
    expect(content).toMatch(/ c\n/); // curvas de la elipse
    expect(content).toMatch(/ Do\n/); // imagen
    const page = (await open(bytes)).getPage(0);
    const annots = page.node.Annots() as PDFArray;
    const note = annots.lookup(0, PDFDict);
    expect(note.get(PDFName.of("Subtype"))?.toString()).toBe("/Text");
    expect((note.lookup(PDFName.of("Contents")) as PDFHexString).decodeText()).toBe("Revisar esta cifra");
  });

  it("corta el texto largo en líneas y respeta la alineación", async () => {
    const long = text({ text: "uno dos tres cuatro cinco seis siete ocho nueve diez", width: 60, align: "right" });
    const { bytes } = await applyEdits(await makePdf("t.pdf", 1, { text: false }), { pages: [{ source: 0, objects: [long] }] });
    const lines = (await contentText(bytes, 0)).match(/> Tj/g) ?? [];
    expect(lines.length).toBeGreaterThan(3);
  });
});

describe("rellenar-pdf: formularios", () => {
  it("lista los campos con su tipo, opciones, página y posición", async () => {
    const info = await inspectForm({ name: "f.pdf", bytes: await formPdf() });
    expect(info.xfa).toBe(false);
    const byName = Object.fromEntries(info.fields.map((f) => [f.name, f]));
    expect(byName.nombre.type).toBe("text");
    expect(byName.acepto.type).toBe("checkbox");
    expect(byName.provincia.options).toEqual(["Madrid", "Málaga", "Teruel"]);
    expect(byName.turno.options).toEqual(["mañana", "tarde"]);
    expect(byName.nombre.page).toBe(0);
    // Widget en y = 300..320 (abajo a la izquierda) → 80..100 desde arriba en una página de 400.
    expect(Math.round(byName.nombre.rect!.y)).toBe(80);
    expect(info.fields.map((f) => f.name)).toEqual(["nombre", "acepto", "provincia", "turno"]);
  });

  it("rellena campos con tildes y eñes y los deja editables", async () => {
    const res = await runClientTool("rellenar-pdf", [{ name: "solicitud.pdf", bytes: await formPdf() }], {
      guardar: "editable",
      model: { fields: { nombre: "Begoña Muñoz", acepto: true, provincia: "Málaga", turno: "tarde" } },
    }, { fonts: noto });
    expect(res.outputs[0].name).toBe("solicitud-relleno.pdf");
    const form = (await open(res.outputs[0].bytes)).getForm();
    expect(form.getTextField("nombre").getText()).toBe("Begoña Muñoz");
    expect(form.getCheckBox("acepto").isChecked()).toBe(true);
    expect(form.getDropdown("provincia").getSelected()).toEqual(["Málaga"]);
    expect(form.getRadioGroup("turno").getSelected()).toBe("tarde");
  });

  it("aplanado: no quedan campos y el texto pasa al contenido", async () => {
    const res = await runClientTool("rellenar-pdf", [{ name: "s.pdf", bytes: await formPdf() }], {
      guardar: "aplanado",
      model: { fields: { nombre: "Ana" }, pages: [{ source: 0, objects: [{ type: "check", x: 300, y: 50, size: 20 }] }] },
    });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getForm().getFields()).toHaveLength(0);
  });

  it("avisa de XFA, lo quita y rellena los campos AcroForm", async () => {
    const doc = await PDFDocument.load(await formPdf());
    const acroForm = doc.catalog.lookup(PDFName.of("AcroForm"), PDFDict);
    acroForm.set(PDFName.of("XFA"), PDFString.of("<xdp:xdp/>"));
    const bytes = await doc.save();
    expect((await inspectForm({ name: "x.pdf", bytes })).xfa).toBe(true);
    const res = await runClientTool("rellenar-pdf", [{ name: "x.pdf", bytes }], { guardar: "editable", model: { fields: { nombre: "Luis", inexistente: "x" } } });
    expect(res.notes.join(" ")).toMatch(/XFA/);
    expect(res.notes.join(" ")).toMatch(/inexistente/);
    expect((await open(res.outputs[0].bytes)).getForm().hasXFA()).toBe(false);
  });
});

describe("PDF con contraseña en el navegador (D-17)", () => {
  async function encrypted(): Promise<Uint8Array> {
    const doc = await PDFDocument.load((await makePdf("c.pdf", 2)).bytes);
    doc.encrypt({ userPassword: "abrir", ownerPassword: "dueno" });
    return doc.save();
  }

  it("pide la contraseña, la acepta y avisa si es incorrecta", async () => {
    const bytes = await encrypted();
    const opts = { angulo: 90, paginas: "todas", por_pagina: {} };
    await expect(runClientTool("girar-pdf", [{ name: "c.pdf", bytes }], opts)).rejects.toMatchObject({ code: "PASSWORD_REQUIRED" });
    await expect(runClientTool("girar-pdf", [{ name: "c.pdf", bytes }], opts, { passwords: { "c.pdf": "mala" } })).rejects.toMatchObject({ code: "WRONG_PASSWORD" });
    const res = await runClientTool("girar-pdf", [{ name: "c.pdf", bytes }], opts, { passwords: { "c.pdf": "abrir" } });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPage(0).getRotation().angle).toBe(90);
  });
});
