import { readFileSync } from "node:fs";

import { PDFDocument, StandardFonts } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

// F4, lote B1: diseñador de campos de hacer-pdf-rellenable y crear-formulario-pdf. Sin campos de firma todo ocurre en el
// navegador (no se sube nada); los campos de firma con pyHanko los prueba pytest (tests/test_formularios.py).

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

async function download(page: Page): Promise<PDFDocument> {
  const link = page.getByRole("region", { name: "Resultado" }).locator("a[download]");
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return PDFDocument.load(readFileSync(await d.path()));
}

/** Coloca un campo con un clic en el punto (fx, fy) de la página, en fracciones de su ancho y alto. */
async function place(page: Page, kind: string, fx: number, fy: number) {
  await page.getByRole("button", { name: kind, exact: true }).click();
  const sheet = page.getByLabel("Página 1");
  const box = (await sheet.boundingBox())!;
  await sheet.click({ position: { x: box.width * fx, y: box.height * fy } }); // desplaza la vista si hace falta
}

test("crear-formulario-pdf: en blanco, texto, casilla y desplegable, sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/crear-formulario-pdf");
  await expect(page.getByRole("heading", { level: 1, name: "Crear un formulario PDF" })).toBeVisible();
  await page.getByRole("button", { name: "Empezar con una página en blanco" }).click();
  await place(page, "Texto", 0.2, 0.2);
  await page.getByLabel("Nombre", { exact: true }).fill("nombre_completo");
  await page.getByLabel("Valor por defecto").fill("Ana");
  await page.getByLabel("Obligatorio").check();
  await place(page, "Casilla", 0.2, 0.3);
  await page.getByLabel("Nombre", { exact: true }).fill("acepto");
  await place(page, "Desplegable", 0.2, 0.4);
  await page.getByLabel("Nombre", { exact: true }).fill("provincia");
  await page.getByLabel("Opciones (una por línea)").fill("Madrid\nTeruel");
  await page.getByLabel("Se puede escribir otro valor").check();
  await expect(page.getByText("3 campos")).toBeVisible();
  await page.getByRole("button", { name: "Guardar el formulario" }).click();
  const doc = await download(page);
  const form = doc.getForm();
  expect(form.getFields().map((f) => f.getName()).sort()).toEqual(["acepto", "nombre_completo", "provincia"]);
  expect(form.getTextField("nombre_completo").getText()).toBe("Ana");
  expect(form.getTextField("nombre_completo").isRequired()).toBe(true);
  expect(form.getDropdown("provincia").getOptions()).toEqual(["Madrid", "Teruel"]);
  expect(form.getDropdown("provincia").isEditable()).toBe(true);
  expect(sent).toEqual([]);
});

test("hacer-pdf-rellenable: campos existentes, duplicar, borrar y detectar líneas", async ({ page }) => {
  const src = await PDFDocument.create();
  const p = src.addPage([400, 500]);
  const font = await src.embedFont(StandardFonts.Helvetica);
  p.drawText("Nombre:", { x: 40, y: 400, size: 12, font });
  p.drawLine({ start: { x: 100, y: 398 }, end: { x: 340, y: 398 }, thickness: 1 });
  src.getForm().createTextField("viejo").addToPage(p, { x: 40, y: 300, width: 120, height: 20 });
  await page.goto("/es/hacer-pdf-rellenable");
  await page.locator('input[type="file"]').setInputFiles({ name: "ficha.pdf", mimeType: "application/pdf", buffer: Buffer.from(await src.save()) });
  await expect(page.getByLabel("Página 1")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("1 campo", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Detectar campos" }).click();
  await expect(page.getByText(/Hay 1 campo sugerido/)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Aceptar todos" }).click();
  await expect(page.getByText("2 campos", { exact: true })).toBeVisible();
  await place(page, "Texto", 0.5, 0.85);
  await page.getByRole("button", { name: "Duplicar" }).click();
  await expect(page.getByText("4 campos", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Borrar" }).click(); // la copia, que queda elegida
  await expect(page.getByText("3 campos", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Guardar el formulario" }).click();
  const doc = await download(page);
  expect(doc.getForm().getFields().map((f) => f.getName()).sort()).toEqual(["Texto 1", "Texto 2", "viejo"]);
});
