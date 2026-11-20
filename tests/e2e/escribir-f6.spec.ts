import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";
import { strFromU8, unzipSync } from "fflate";

// escribir-pdf (A.1, F6-O1, D-234) en Chromium: el editor, Word y Markdown en el navegador y el borrador en IndexedDB.
// El PDF lo hace el servidor (tests/test_escribir.py).

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`));
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().startsWith("CSP")) throw new Error(m.text());
  });
});

async function open(page: Page) {
  await page.goto("/es/escribir-pdf");
  const editor = page.locator("[data-escribir-editor]");
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await page.locator('[data-plantilla="blanco"]').click();
  return editor;
}

async function downloadOf(page: Page, selector: string): Promise<{ name: string; bytes: Buffer }> {
  const [file] = await Promise.all([page.waitForEvent("download"), page.locator(selector).click()]);
  return { name: file.suggestedFilename(), bytes: readFileSync(await file.path()) };
}

test("escribir-pdf: títulos, tabla, índice, nota, fórmula y campo, a Word y a Markdown", async ({ page }) => {
  const editor = await open(page);
  await editor.click();
  await page.getByLabel("Tipo de párrafo").selectOption("h1");
  await page.keyboard.type("Informe de prueba");
  await page.keyboard.press("Enter");
  await page.locator('[data-tool="indice"]').click();
  await page.getByLabel("Tipo de párrafo").selectOption("h2");
  await page.keyboard.type("Datos del año");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Texto en ");
  await page.locator('[data-tool="negrita"]').click();
  await page.keyboard.type("negrita");
  await page.locator('[data-tool="negrita"]').click();
  await page.locator('[data-tool="nota"]').click();
  await page.getByLabel("Texto de la nota").fill("Fuente propia");
  await page.getByRole("button", { name: "Insertar" }).click();
  await page.locator('[data-tool="formula"]').click();
  await page.getByLabel("Fórmula en LaTeX").fill("E=mc^2");
  await page.getByRole("button", { name: "Insertar" }).click();
  await page.locator('[data-tool="campo"]').click();
  await page.getByLabel("Nombre del campo").fill("Firma");
  await page.getByRole("button", { name: "Insertar" }).click();
  await page.locator('[data-tool="tabla"]').click();
  await page.keyboard.type("Columna A");
  // El índice del editor ya muestra los dos títulos.
  await expect(page.locator("nav.indice-editor")).toContainText("Informe de prueba");
  await expect(page.locator("nav.indice-editor")).toContainText("Datos del año");
  await expect(page.locator(".katex").first()).toBeVisible();

  const md = await downloadOf(page, '[data-exportar="md"]');
  const text = md.bytes.toString("utf-8");
  expect(md.name).toBe("Informe de prueba.md");
  expect(text).toContain("# Informe de prueba");
  expect(text).toContain("- [Datos del año](#datos-del-ano)");
  expect(text).toContain("**negrita**[^1]$E=mc^2$");
  expect(text).toContain("[^1]: Fuente propia");
  expect(text).toMatch(/\| Columna A \|/);

  const docx = await downloadOf(page, '[data-exportar="docx"]');
  expect(docx.name).toBe("Informe de prueba.docx");
  const files = unzipSync(new Uint8Array(docx.bytes));
  const xml = strFromU8(files["word/document.xml"]);
  expect(xml).toContain("Informe de prueba");
  expect(xml).toContain("w:footnoteReference");
  expect(xml).toContain("TOC");
});

test("escribir-pdf: buscar y reemplazar, plantillas y borrador que se recupera", async ({ page }) => {
  const editor = await open(page);
  await editor.click();
  await page.keyboard.type("hola mundo, hola de nuevo");
  await page.locator('[data-tool="buscar"]').click();
  await page.getByLabel("Buscar", { exact: true }).fill("hola");
  await page.getByLabel("Reemplazar por").fill("adiós");
  await page.locator("[data-reemplazar-todo]").click();
  await expect(editor).toContainText("adiós mundo, adiós de nuevo");
  await expect(page.locator("[data-escribir-status]")).toHaveText("2 reemplazos.");
  await page.waitForTimeout(2200); // guardado automático del borrador
  await page.reload();
  await expect(page.locator("[data-escribir-editor]")).toContainText("adiós mundo", { timeout: 30_000 });
  await page.locator('[data-plantilla="solicitud"]').click();
  await expect(page.locator("[data-escribir-editor]")).toContainText("Datos del solicitante");
  await expect(page.locator(".campo-editor").first()).toBeVisible();
});
