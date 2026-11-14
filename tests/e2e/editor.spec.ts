import { readFileSync } from "node:fs";

import { PDFDict, PDFDocument, PDFName, PDFString, StandardFonts, extractPageContents } from "@cantoo/pdf-lib";
import { expect, test, type Page, type Request } from "@playwright/test";

function watchUploads(page: Page): Request[] {
  const sent: Request[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r);
  });
  return sent;
}

async function pdfText(bytes: Buffer): Promise<string[]> {
  const doc = await PDFDocument.load(bytes);
  return doc.getPages().map((p) => extractPageContents(p.node).filter((a) => a.kind === "text").map((a) => (a.kind === "text" ? a.getText() : "")).join(" "));
}

async function samplePdf(pages: number): Promise<Buffer> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < pages; i += 1) doc.addPage([400, 500]).drawText(`Hoja ${i + 1}`, { x: 40, y: 450, size: 20, font });
  return Buffer.from(await doc.save());
}

async function formPdf(): Promise<Buffer> {
  const doc = await PDFDocument.create();
  const page = doc.addPage([400, 400]);
  const form = doc.getForm();
  form.createTextField("nombre").addToPage(page, { x: 20, y: 300, width: 200, height: 20 });
  form.createCheckBox("acepto").addToPage(page, { x: 20, y: 250, width: 15, height: 15 });
  const provincia = form.createDropdown("provincia");
  provincia.setOptions(["Madrid", "Málaga", "Teruel"]);
  provincia.addToPage(page, { x: 20, y: 200, width: 150, height: 20 });
  return Buffer.from(await doc.save());
}

async function saveAndDownload(page: Page): Promise<Buffer> {
  await page.getByRole("button", { name: "Guardar PDF" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return readFileSync(await download.path());
}

test("editar-pdf: página en blanco con texto, rectángulo y firma escrita", async ({ page }) => {
  // Ventana alta: la hoja entera queda a la vista, debajo de la barra de herramientas.
  await page.setViewportSize({ width: 1280, height: 1800 });
  await page.goto("/es/editar-pdf");
  const sent = watchUploads(page);
  await page.getByRole("button", { name: "Empezar con una página en blanco" }).click();
  const sheet = page.locator("svg[viewBox]").first();
  await expect(sheet).toBeVisible();

  await page.getByRole("button", { name: "Texto", exact: true }).click();
  await sheet.scrollIntoViewIfNeeded();
  const box = (await sheet.boundingBox())!;
  await sheet.click({ position: { x: box.width * 0.2, y: box.height * 0.2 } });
  await page.getByRole("textbox", { name: "Texto" }).fill("Hola editor, España");
  await page.getByRole("button", { name: "Seleccionar y mover" }).click();

  await page.getByRole("button", { name: "Rectángulo", exact: true }).click();
  const area = (await sheet.boundingBox())!;
  await page.mouse.move(area.x + area.width * 0.2, area.y + area.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width * 0.6, area.y + area.height * 0.55, { steps: 5 });
  await page.mouse.up();

  await page.getByRole("button", { name: "Firma", exact: true }).click();
  await page.getByRole("tab", { name: "Escribir" }).click();
  await page.getByLabel("Tu nombre").fill("Ana García");
  await page.getByRole("button", { name: "Usar la firma" }).click();

  const bytes = await saveAndDownload(page);
  const doc = await PDFDocument.load(bytes);
  expect(doc.getPageCount()).toBe(1);
  expect(Math.round(doc.getPage(0).getWidth())).toBe(595);
  expect((await pdfText(bytes))[0]).toContain("Hola editor, España");
  const assets = extractPageContents(doc.getPage(0).node);
  expect(assets.some((a) => a.kind === "image")).toBe(true);
  expect(sent.map((r) => r.url())).toEqual([]);
});

test("editar-pdf: borrar, girar e insertar páginas", async ({ page }) => {
  await page.goto("/es/editar-pdf");
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({ name: "hojas.pdf", mimeType: "application/pdf", buffer: await samplePdf(3) });
  await expect(page.getByLabel("Página 3", { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Borrar la página 2" }).click();
  await page.getByRole("button", { name: "Girar la página 1" }).click();
  await page.getByRole("button", { name: "Insertar una página en blanco tras la 2" }).click();
  await page.getByRole("button", { name: "Subir la página 2" }).click();
  const bytes = await saveAndDownload(page);
  const doc = await PDFDocument.load(bytes);
  expect(doc.getPageCount()).toBe(3);
  const text = await pdfText(bytes);
  // Orden final: Hoja 3, Hoja 1 (girada) y la página en blanco.
  expect(text[0]).toContain("Hoja 3");
  expect(text[1]).toContain("Hoja 1");
  expect(doc.getPage(1).getRotation().angle).toBe(90);
  expect(text[2].trim()).toBe("");
});

test("rellenar-pdf: campos con tildes, casilla y desplegable", async ({ page }) => {
  await page.goto("/es/rellenar-pdf");
  const sent = watchUploads(page);
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({ name: "solicitud.pdf", mimeType: "application/pdf", buffer: await formPdf() });
  await expect(page.getByRole("heading", { name: "Campos del formulario" })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("nombre · Página 1").fill("Begoña Muñoz");
  await page.getByLabel("acepto · Página 1").check();
  await page.getByLabel("provincia · Página 1").selectOption("Málaga");
  const bytes = await saveAndDownload(page);
  const form = (await PDFDocument.load(bytes)).getForm();
  expect(form.getTextField("nombre").getText()).toBe("Begoña Muñoz");
  expect(form.getCheckBox("acepto").isChecked()).toBe(true);
  expect(form.getDropdown("provincia").getSelected()).toEqual(["Málaga"]);
  expect(sent).toEqual([]);
});

test("PDF con contraseña en una herramienta de navegador (D-17)", async ({ page }) => {
  const doc = await PDFDocument.load(await samplePdf(2));
  doc.encrypt({ userPassword: "abrir", ownerPassword: "dueno" });
  const encrypted = Buffer.from(await doc.save());
  await page.goto("/es/girar-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "cifrado.pdf", mimeType: "application/pdf", buffer: encrypted });
  await page.getByRole("button", { name: "Empezar" }).click();
  await expect(page.getByText("Contraseña de cifrado.pdf")).toBeVisible({ timeout: 30_000 });
  await page.locator('input[type="password"]').fill("mala");
  await page.locator('input[type="password"]').press("Enter");
  await expect(page.getByText("La contraseña no es correcta.")).toBeVisible({ timeout: 30_000 });
  await page.locator('input[type="password"]').fill("abrir");
  await page.locator('input[type="password"]').press("Enter");
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const out = await PDFDocument.load(readFileSync(await download.path()));
  expect(out.getPage(0).getRotation().angle).toBe(90);
});

test("redactar-pdf: buscar, redactar todas las coincidencias y comprobar el resultado", async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1400 });
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const p1 = doc.addPage([400, 400]);
  p1.drawText("Cliente: Juan Pérez García", { x: 40, y: 330, size: 14, font });
  p1.drawText("DNI 12345678Z", { x: 40, y: 300, size: 12, font });
  doc.addPage([400, 400]).drawText("Segunda hoja sin datos", { x: 40, y: 330, size: 14, font });
  const sent = watchUploads(page);
  await page.goto("/es/redactar-pdf");
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({ name: "cliente.pdf", mimeType: "application/pdf", buffer: Buffer.from(await doc.save()) });
  await expect(page.getByRole("heading", { name: "Redacción" })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Buscar texto").fill("juan perez");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.getByText("1 coincidencia")).toBeVisible();
  await page.getByRole("button", { name: "Redactar todas las coincidencias" }).click();
  await page.getByRole("button", { name: "Redactar los patrones marcados" }).click();
  await expect(page.getByRole("button", { name: "Quitar el área" })).toHaveCount(2);
  const bytes = await saveAndDownload(page);
  const text = await pdfText(bytes);
  expect(text[0]).not.toContain("Juan");
  expect(text[0]).not.toContain("12345678Z");
  expect(text[1]).toContain("Segunda hoja sin datos");
  expect(sent).toEqual([]);
});

test("redactar-pdf: «eliminar solo el contenido bajo el área» conserva el resto del texto (D-153)", async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1400 });
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  doc.addPage([400, 400]).drawText("Cliente: Juan Pérez García", { x: 40, y: 330, size: 14, font });
  const sent = watchUploads(page);
  await page.goto("/es/redactar-pdf");
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({ name: "cliente.pdf", mimeType: "application/pdf", buffer: Buffer.from(await doc.save()) });
  await expect(page.getByRole("heading", { name: "Redacción" })).toBeVisible({ timeout: 30_000 });
  // Por defecto, rasterizar (A.6).
  await expect(page.getByLabel("rasterizar las páginas afectadas a 300 ppp")).toBeChecked();
  await page.getByLabel("eliminar solo el contenido bajo el área").check();
  await page.getByLabel("Buscar texto").fill("juan perez");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.getByRole("button", { name: "Redactar todas las coincidencias" }).click();
  const bytes = await saveAndDownload(page);
  const text = await pdfText(bytes);
  expect(text[0]).not.toContain("Juan");
  expect(text[0]).toContain("Cliente:");
  await expect(page.getByText(/^Se ha eliminado el contenido bajo las áreas en las páginas 1/)).toBeVisible();
  expect(sent).toEqual([]);
});

test("varias-paginas-por-hoja y recortar en el navegador", async ({ page }) => {
  await page.goto("/es/varias-paginas-por-hoja");
  await page.locator('input[type="file"]').setInputFiles({ name: "cuatro.pdf", mimeType: "application/pdf", buffer: await samplePdf(4) });
  await page.getByLabel("Páginas por hoja").selectOption("4");
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const out = readFileSync(await download.path());
  expect((await PDFDocument.load(out)).getPageCount()).toBe(1);

  await page.goto("/es/recortar-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "margen.pdf", mimeType: "application/pdf", buffer: await samplePdf(1) });
  await page.getByLabel("Recortar automáticamente los márgenes blancos").check();
  await page.getByRole("button", { name: "Empezar" }).click();
  const link2 = page.locator("a[download]").first();
  await expect(link2).toBeVisible({ timeout: 30_000 });
  const [download2] = await Promise.all([page.waitForEvent("download"), link2.click()]);
  const box = (await PDFDocument.load(readFileSync(await download2.path()))).getPage(0).getCropBox();
  expect(box.width).toBeLessThan(200);
  expect(box.height).toBeLessThan(100);
});

test("anotar-pdf: resaltado y nota como anotaciones estándar, lista de comentarios y XFDF", async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1600 });
  const sent = watchUploads(page);
  await page.goto("/es/anotar-pdf");
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({ name: "notas.pdf", mimeType: "application/pdf", buffer: await samplePdf(1) });
  const sheet = page.locator("svg[viewBox]").first();
  await expect(sheet).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Autor").fill("Ana");

  await page.getByRole("button", { name: "Resaltar", exact: true }).click();
  await sheet.scrollIntoViewIfNeeded();
  const area = (await sheet.boundingBox())!;
  await page.mouse.move(area.x + area.width * 0.08, area.y + area.height * 0.06);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width * 0.5, area.y + area.height * 0.13, { steps: 5 });
  await page.mouse.up();

  await page.getByRole("button", { name: "Nota", exact: true }).click();
  await sheet.click({ position: { x: area.width * 0.7, y: area.height * 0.3 } });
  await page.getByRole("textbox", { name: "Nota" }).fill("Revisar esta hoja");
  await page.getByRole("button", { name: "Seleccionar y mover" }).click();

  const comments = page.getByRole("complementary", { name: "Comentarios" });
  await expect(comments.getByText(/Resaltar · Página 1/)).toBeVisible();
  await expect(comments.getByText(/Revisar esta hoja/)).toBeVisible();

  const [xfdfDownload] = await Promise.all([page.waitForEvent("download"), comments.getByRole("button", { name: "Exportar comentarios (XFDF)" }).click()]);
  const xfdf = readFileSync(await xfdfDownload.path(), "utf8");
  expect(xfdf).toContain("<highlight");
  expect(xfdf).toContain("Revisar esta hoja");

  const bytes = await saveAndDownload(page);
  const doc = await PDFDocument.load(bytes);
  const annots = doc.getPage(0).node.Annots();
  const subtypes = (annots?.asArray() ?? []).map((ref) => String((doc.context.lookup(ref) as PDFDict).get(PDFName.of("Subtype"))));
  expect(subtypes).toEqual(expect.arrayContaining(["/Highlight", "/Text"]));
  expect(sent).toEqual([]);
});

test("lector-pdf: abre, busca, cambia el zoom, salta de página y descarga sin subir nada", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  const sent = watchUploads(page);
  await page.goto("/es/lector-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "tres.pdf", mimeType: "application/pdf", buffer: await samplePdf(3) });
  await expect(page.getByText("de 3", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-page="1"] canvas[data-rendered="1"]')).toHaveCount(1, { timeout: 30_000 });

  await page.getByLabel("Buscar en el documento").fill("hoja 3");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.getByText("1 de 1")).toBeVisible();
  await expect(page.locator('[data-page="3"] [data-active-match]')).toHaveCount(1);

  await page.getByLabel("Zoom", { exact: true }).selectOption("2");
  const width = await page.locator('[data-page="1"]').evaluate((el) => el.getBoundingClientRect().width);
  expect(Math.round(width)).toBe(Math.round(((400 * 96) / 72) * 2));

  await page.getByLabel("Página", { exact: true }).fill("2");
  await page.getByLabel("Página", { exact: true }).press("Enter");
  await expect(page.locator('[data-page="2"] canvas[data-rendered="1"]')).toHaveCount(1, { timeout: 30_000 });

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Descargar" }).click()]);
  expect((await PDFDocument.load(readFileSync(await download.path()))).getPageCount()).toBe(3);
  expect(sent).toEqual([]);
});

test("lector-pdf: miniaturas, marcadores y texto seleccionable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto("/es/lector-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "tres.pdf", mimeType: "application/pdf", buffer: await samplePdf(3) });
  await expect(page.locator('[data-page="1"] .text-layer span').first()).toHaveText(/Hoja 1/, { timeout: 30_000 });
  // El texto se puede seleccionar: la selección del navegador lo devuelve.
  const selected = await page.locator('[data-page="1"] .text-layer span').first().evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    return sel.toString();
  });
  expect(selected).toContain("Hoja 1");

  await page.getByRole("button", { name: "Panel lateral" }).click();
  await expect(page.locator("[data-thumb]")).toHaveCount(3);
  await page.locator('[data-thumb="3"]').click();
  await expect(page.getByLabel("Página", { exact: true })).toHaveValue("3");
  await page.getByRole("tab", { name: "Marcadores" }).click();
  await expect(page.getByText("Este PDF no tiene marcadores.")).toBeVisible();
});

test("lector-pdf: los enlaces del PDF se pueden pulsar (D-23 y D-152)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  const sent = watchUploads(page);
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const pages = [doc.addPage([400, 500]), doc.addPage([400, 500]), doc.addPage([400, 500])];
  pages.forEach((p, i) => p.drawText(`Hoja ${i + 1}`, { x: 40, y: 450, size: 20, font }));
  const link = (dict: Record<string, unknown>) => pages[0].node.addAnnot(doc.context.register(doc.context.obj({ Type: "Annot", Subtype: "Link", ...dict })));
  link({ Rect: [40, 380, 200, 400], Dest: [pages[2].ref, PDFName.of("Fit")] });
  link({ Rect: [40, 330, 200, 350], A: { S: "URI", URI: PDFString.of("https://example.com/informe") } });
  link({ Rect: [40, 280, 200, 300], A: { S: "URI", URI: PDFString.of("javascript:alert(1)") } });
  await page.goto("/es/lector-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "enlaces.pdf", mimeType: "application/pdf", buffer: Buffer.from(await doc.save()) });
  const internal = page.locator('[data-page="1"] [data-pdf-link="internal"]');
  await expect(internal).toHaveCount(1, { timeout: 30_000 });
  const external = page.locator('[data-page="1"] [data-pdf-link="external"]');
  // El de javascript: no se ofrece.
  await expect(external).toHaveCount(1);
  await expect(external).toHaveAttribute("href", "https://example.com/informe");
  await expect(external).toHaveAttribute("target", "_blank");
  await expect(external).toHaveAttribute("rel", /noopener/);
  await expect(page.getByRole("link", { name: "Ir a la página 3" })).toBeVisible();
  await internal.click();
  await expect(page.getByLabel("Página", { exact: true })).toHaveValue("3");
  expect(sent).toEqual([]);
});

test("recortar-pdf en modo visual y folleto con vista previa, hojeado e impresión", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1400 });
  await page.goto("/es/recortar-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "margen.pdf", mimeType: "application/pdf", buffer: await samplePdf(1) });
  await page.getByLabel("Modo visual (rectángulo sobre la vista previa)").check();
  const preview = page.locator("[data-crop-preview]");
  await expect(preview.locator('canvas[data-rendered="1"]')).toHaveCount(1, { timeout: 30_000 });
  await preview.scrollIntoViewIfNeeded();
  const box = (await preview.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.1);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5, { steps: 6 });
  await page.mouse.up();
  // 10 % de 400 pt = 40 pt ≈ 14,1 mm.
  expect(Number(await page.getByLabel("Izquierda (mm)").inputValue())).toBeCloseTo(14.1, 0);
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const crop = (await PDFDocument.load(readFileSync(await download.path()))).getPage(0).getCropBox();
  expect(crop.width).toBeGreaterThan(190);
  expect(crop.width).toBeLessThan(210);

  await page.goto("/es/folleto-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "seis.pdf", mimeType: "application/pdf", buffer: await samplePdf(6) });
  await page.getByRole("button", { name: "Empezar" }).click();
  const booklet = page.getByRole("region", { name: "Vista previa del folleto" });
  // 6 páginas → 8 con blancos → 2 hojas de dos caras.
  await expect(booklet.locator("[data-sheet]")).toHaveCount(4, { timeout: 30_000 });
  await booklet.getByRole("tab", { name: "Hojear" }).click();
  await expect(booklet.locator('[data-spread="1"] canvas')).toHaveCount(1, { timeout: 30_000 });
  await booklet.getByRole("button", { name: "Siguiente" }).click();
  await expect(booklet.locator('[data-spread="2"] canvas')).toHaveCount(2);
  await page.getByRole("button", { name: "Imprimir" }).first().click();
  await expect(page.locator("iframe[data-print]")).toHaveCount(1);
});
