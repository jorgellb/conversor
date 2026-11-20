import { readFileSync } from "node:fs";

import {
  PDFButton, PDFCheckBox, PDFDict, PDFDocument, PDFDropdown, PDFName, PDFOptionList, PDFRadioGroup, PDFString, PDFTextField, StandardFonts, degrees,
} from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { detectFields, inspectForm, runClientTool, type DesignField } from "../src/index";
import { designForm, userRect } from "../src/forms";

const noto = async () => new Uint8Array(readFileSync(new URL("../../../apps/web/public/fonts/NotoSans-Regular.ttf", import.meta.url)));

function field(overrides: Partial<DesignField>): DesignField {
  return { type: "text", name: "campo", page: 0, x: 50, y: 60, width: 200, height: 20, ...overrides };
}

async function existingForm(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const page = doc.addPage([400, 400]);
  const form = doc.getForm();
  form.createTextField("viejo").addToPage(page, { x: 20, y: 300, width: 100, height: 20 });
  form.createTextField("borrar").addToPage(page, { x: 20, y: 250, width: 100, height: 20 });
  return doc.save();
}

describe("hacer-pdf-rellenable (A.3)", () => {
  it("crea cada tipo de campo con sus propiedades", async () => {
    const fields: DesignField[] = [
      field({ name: "nombre", defaultValue: "Ana", required: true, maxLength: 20, align: "center", fontSize: 11, border: "#000000", background: "#FFFFCC" }),
      field({ name: "notas", y: 100, height: 60, multiline: true, readOnly: true }),
      field({ type: "checkbox", name: "acepto", y: 180, width: 14, height: 14, defaultValue: true }),
      field({ type: "radio", name: "turno", y: 210, height: 40, options: ["mañana", "tarde"], defaultValue: "tarde" }),
      field({ type: "dropdown", name: "provincia", y: 260, options: ["Madrid", "Teruel"], editable: true, defaultValue: "Soria" }),
      field({ type: "optionlist", name: "idiomas", y: 290, height: 50, options: ["es", "en", "fr"], multiSelect: true, defaultValue: ["es", "fr"] }),
      field({ type: "button", name: "limpiar", y: 350, width: 80, action: "reset", label: "Borrar" }),
      field({ type: "button", name: "web", x: 150, y: 350, width: 80, action: "url", url: "https://example.org/ayuda" }),
      field({ type: "signature", name: "firma", y: 400, width: 180, height: 50 }),
    ];
    const { bytes, signatures } = await designForm(null, { blank: [[595, 842]], fields });
    const doc = await PDFDocument.load(bytes);
    const form = doc.getForm();
    const nombre = form.getTextField("nombre");
    expect(nombre.getText()).toBe("Ana");
    expect(nombre.isRequired()).toBe(true);
    expect(nombre.getMaxLength()).toBe(20);
    expect(form.getTextField("notas").isMultiline()).toBe(true);
    expect(form.getTextField("notas").isReadOnly()).toBe(true);
    expect(form.getCheckBox("acepto").isChecked()).toBe(true);
    expect(form.getRadioGroup("turno").getOptions()).toEqual(["mañana", "tarde"]);
    expect(form.getRadioGroup("turno").getSelected()).toBe("tarde");
    expect(form.getDropdown("provincia").isEditable()).toBe(true);
    expect(form.getDropdown("provincia").getSelected()).toEqual(["Soria"]);
    expect(form.getOptionList("idiomas").isMultiselect()).toBe(true);
    expect(form.getOptionList("idiomas").getSelected().sort()).toEqual(["es", "fr"]);
    const action = (name: string) => form.getButton(name).acroField.getWidgets()[0].dict.lookup(PDFName.of("A"), PDFDict);
    expect(action("limpiar").get(PDFName.of("S"))).toEqual(PDFName.of("ResetForm"));
    expect((action("web").lookup(PDFName.of("URI")) as PDFString).decodeText()).toBe("https://example.org/ayuda");
    // La firma no la crea el navegador: va al servidor con su rectángulo en el espacio de usuario (origen abajo).
    expect(form.getFields().map((f) => f.getName())).not.toContain("firma");
    expect(signatures).toEqual([{ name: "firma", page: 0, box: [50, 842 - 450, 230, 842 - 400] }]);
    const kinds = form.getFields().map((f) => f.constructor);
    for (const k of [PDFTextField, PDFCheckBox, PDFRadioGroup, PDFDropdown, PDFOptionList, PDFButton]) expect(kinds).toContain(k);
  });

  it("mueve, borra y conserva los campos que ya tenía el PDF", async () => {
    const { bytes } = await designForm({ name: "a.pdf", bytes: await existingForm() }, {
      remove: ["borrar"], move: [{ name: "viejo", x: 10, y: 10, width: 150, height: 30 }], fields: [field({ name: "nuevo" })],
    });
    const info = await inspectForm({ name: "b.pdf", bytes });
    expect(info.fields.map((f) => f.name).sort()).toEqual(["nuevo", "viejo"]);
    const viejo = info.fields.find((f) => f.name === "viejo");
    expect(viejo?.rect).toEqual({ x: 10, y: 10, width: 150, height: 30 });
  });

  it("rechaza nombres repetidos, nombres con punto, URL peligrosas y opciones vacías", async () => {
    const base = { name: "a.pdf", bytes: await existingForm() };
    await expect(designForm(base, { fields: [field({ name: "viejo" })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ name: "a" }), field({ name: "a" })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ name: "a.b" })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ type: "button", name: "x", action: "url", url: "javascript:alert(1)" })] }))
      .rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ type: "dropdown", name: "d", options: [" "] })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ page: 3 })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });

  it("en una página girada el campo queda donde se ve", async () => {
    const doc = await PDFDocument.create();
    doc.addPage([400, 600]).setRotation(degrees(90));
    const bytes = await doc.save();
    const { bytes: out } = await designForm({ name: "g.pdf", bytes }, { fields: [field({ name: "t", x: 30, y: 40, width: 100, height: 20 })] });
    const info = await inspectForm({ name: "g.pdf", bytes: out });
    const rect = info.fields[0].rect!;
    expect([rect.x, rect.y, rect.width, rect.height].map(Math.round)).toEqual([30, 40, 100, 20]);
  });

  it("usa una fuente completa si los textos no caben en Helvetica", async () => {
    await expect(designForm(null, { fields: [field({ defaultValue: "Ελληνικά" })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    const { bytes } = await designForm(null, { fields: [field({ defaultValue: "Ελληνικά" })] }, async () => noto());
    expect((await PDFDocument.load(bytes)).getForm().getTextField("campo").getText()).toBe("Ελληνικά");
  });

  it("la herramienta devuelve el PDF y los campos de firma", async () => {
    const result = await runClientTool("crear-formulario-pdf", [], { design: { fields: [field({ type: "signature", name: "Firma 1" })] } }, {});
    expect(result.outputs[0].name).toBe("formulario.pdf");
    expect(result.data?.signatures).toHaveLength(1);
  });

  it("userRect lleva la vista al espacio de usuario", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([200, 300]);
    expect(userRect(page, 10, 20, 50, 30)).toEqual({ x: 10, y: 250, width: 50, height: 30 });
    await doc.embedFont(StandardFonts.Helvetica);
  });
});

describe("detección de campos (A.3, Extra)", () => {
  function canvas(width: number, height: number) {
    const rgba = new Uint8ClampedArray(width * height * 4).fill(255);
    const dark = (x: number, y: number) => rgba.set([0, 0, 0, 255], (y * width + x) * 4);
    return { rgba, dark };
  }

  it("encuentra una línea para escribir y una casilla vacía, y no un texto", () => {
    const scale = 2;
    const { rgba, dark } = canvas(600, 400);
    for (let x = 100; x < 400; x += 1) dark(x, 200); // línea de 150 pt
    for (let k = 0; k <= 24; k += 1) { dark(100 + k, 300); dark(100 + k, 324); dark(100, 300 + k); dark(124, 300 + k); } // casilla de 12,5 pt
    for (let x = 100; x < 400; x += 3) for (let y = 50; y < 60; y += 1) dark(x, y); // «texto»: trazos cortos, no línea
    // Una caja de 200 × 30 pt (el borde de un campo): ni su lado de arriba ni el de abajo son líneas para escribir.
    for (let x = 300; x <= 500; x += 1) { dark(x, 320); dark(x, 380); }
    for (let y = 320; y <= 380; y += 1) { dark(300, y); dark(500, y); }
    const found = detectFields(rgba, 600, 400, scale);
    expect(found).toEqual([
      { type: "text", x: 50, y: 86, width: 150, height: 14 },
      { type: "checkbox", x: 50, y: 150, width: 12.5, height: 12.5 },
    ]);
  });
});

describe("firmar-pdf, insertar firma (A.6)", () => {
  it("pone la imagen de la firma y la fecha en las páginas elegidas y nombra el resultado", async () => {
    const { PNG_30x30, b64 } = await import("./images.fixture");
    const src = await PDFDocument.create();
    src.addPage([400, 400]);
    src.addPage([400, 400]);
    const png = b64(PNG_30x30);
    const sig = { type: "image" as const, x: 250, y: 300, width: 120, height: 40, data: png, format: "png" as const };
    const date = { type: "text" as const, x: 250, y: 350, width: 100, text: "20/11/2026", font: "sans" as const, size: 10, color: "#000000" };
    const result = await runClientTool("firmar-pdf", [{ name: "contrato.pdf", bytes: await src.save() }],
      { model: { pages: [{ source: 0, objects: [sig] }, { source: 1, objects: [sig, date] }] } }, {});
    expect(result.outputs[0].name).toBe("contrato-firmado.pdf");
    const out = await PDFDocument.load(result.outputs[0].bytes);
    expect(out.getPageCount()).toBe(2);
    for (const page of out.getPages()) expect(page.node.Resources()?.toString()).toContain("/XObject");
  });
});

describe("revisión de F4-B1 (D-198)", () => {
  it("guarda /DV, no marca MultiSelect en un desplegable editable y no vuelve editable uno que no lo es", async () => {
    const { bytes } = await designForm(null, { fields: [
      field({ name: "t", defaultValue: "Hola" }),
      field({ type: "checkbox", name: "c", y: 100, width: 14, height: 14, defaultValue: true }),
      field({ type: "dropdown", name: "d1", y: 140, options: ["A", "B"], editable: true, defaultValue: "Z" }),
      field({ type: "dropdown", name: "d2", y: 180, options: ["A", "B"], defaultValue: "Z" }),
    ] });
    const form = (await PDFDocument.load(bytes)).getForm();
    for (const name of ["t", "c", "d1"]) expect(form.getField(name).acroField.dict.has(PDFName.of("DV"))).toBe(true);
    const d1 = form.getDropdown("d1");
    expect(d1.isEditable()).toBe(true);
    expect(d1.isMultiselect()).toBe(false);
    expect(d1.getSelected()).toEqual(["Z"]);
    expect(form.getDropdown("d2").isEditable()).toBe(false);
    expect(form.getDropdown("d2").getSelected()).toEqual([]);
  });

  it("un nombre nuevo no puede chocar con el antepasado de uno existente, y el borde no agranda el widget", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([400, 400]);
    doc.getForm().createTextField("persona.nombre").addToPage(page, { x: 10, y: 10, width: 100, height: 20 });
    await expect(designForm({ name: "a.pdf", bytes: await doc.save() }, { fields: [field({ name: "persona" })] }))
      .rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    const { bytes } = await designForm(null, { blank: [[400, 400]], fields: [field({ name: "b", x: 20, y: 30, width: 150, height: 24, border: "#000000" })] });
    const info = await inspectForm({ name: "b.pdf", bytes });
    expect(info.fields[0].rect).toEqual({ x: 20, y: 30, width: 150, height: 24 });
  });

  it("rechaza campos fuera de la página, grupos de opciones demasiado bajos y URL mal escritas", async () => {
    await expect(designForm(null, { blank: [[400, 400]], fields: [field({ x: -500 })] })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { blank: [[400, 400]], fields: [field({ type: "radio", height: 20, options: ["a", "b", "c"] })] }))
      .rejects.toMatchObject({ code: "INVALID_OPTIONS" });
    await expect(designForm(null, { fields: [field({ type: "button", name: "u", action: "url", url: "https://example.org/%E0%A4%A" })] }))
      .rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });

  it("informa de los widgets y de las firmas existentes, y al mover un campo regenera su apariencia", async () => {
    const doc = await PDFDocument.create();
    const p1 = doc.addPage([400, 400]);
    const p2 = doc.addPage([400, 400]);
    const repeated = doc.getForm().createTextField("repetido");
    repeated.addToPage(p1, { x: 10, y: 10, width: 100, height: 20 });
    repeated.addToPage(p2, { x: 10, y: 10, width: 100, height: 20 });
    const single = doc.getForm().createTextField("solo");
    single.setText("Hola mundo");
    single.addToPage(p1, { x: 10, y: 100, width: 100, height: 20 });
    const bytes = await doc.save();
    const info = await inspectForm({ name: "r.pdf", bytes });
    expect(info.fields.find((f) => f.name === "repetido")?.widgets).toBe(2);
    expect(info.signed).toBe(false);
    const { bytes: out } = await designForm({ name: "r.pdf", bytes }, { move: [{ name: "solo", x: 10, y: 200, width: 250, height: 40 }], fields: [] });
    const outDoc = await PDFDocument.load(out);
    const moved = outDoc.getForm().getTextField("solo").acroField.getWidgets()[0];
    const ap = outDoc.context.lookup(moved.getNormalAppearance() as never) as unknown as { dict: { lookup(n: PDFName): unknown } };
    const bbox = String(ap.dict.lookup(PDFName.of("BBox")));
    expect(bbox).toContain("250");
  });
});
