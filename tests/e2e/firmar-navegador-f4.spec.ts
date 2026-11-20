import { readFileSync } from "node:fs";

import { PDFDocument, PDFName, PDFDict } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

// F4, lote B2a: firmar-pdf en el navegador («Insertar firma»: firma escrita, iniciales, fecha y repetir en varias
// páginas). El sello y el certificado propio del servidor los prueba pytest (tests/test_sello.py y
// tests/test_firma_propia.py) y la apertura del .p12, vitest (apps/web/test/p12.test.ts).

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test("firmar-pdf: firma escrita repetida en todas las páginas, sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  const src = await PDFDocument.create();
  src.addPage([400, 500]);
  src.addPage([400, 500]);
  await page.goto("/es/firmar-pdf");
  await expect(page.getByRole("heading", { level: 1, name: "Firmar PDF" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({ name: "contrato.pdf", mimeType: "application/pdf", buffer: Buffer.from(await src.save()) });
  await page.getByRole("button", { name: "Firma", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Firma" });
  await dialog.getByRole("tab", { name: "Escribir" }).click();
  await dialog.getByLabel("Tu nombre").fill("Ana Pérez");
  await expect(dialog.getByRole("tab", { name: "Cámara" })).toBeVisible();
  await dialog.getByRole("button", { name: "Usar la firma" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Repetir lo elegido" }).click();
  await page.getByRole("radio", { name: "Firmar digitalmente" }).check();
  await expect(page.getByLabel("Nivel PAdES")).toHaveValue("B-T");
  await page.getByRole("radio", { name: "Insertar firma" }).check();
  await page.getByRole("button", { name: "Guardar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(d.suggestedFilename()).toBe("contrato-firmado.pdf");
  const out = await PDFDocument.load(readFileSync(await d.path()));
  for (const p of out.getPages()) {
    const xobjects = p.node.Resources()?.lookup(PDFName.of("XObject"), PDFDict);
    expect(xobjects?.keys().length ?? 0).toBeGreaterThan(0);
  }
  expect(sent).toEqual([]);
});

// F4-Z (D-210): la firma dibujada o escrita puede ir dentro de la apariencia del sello digital.
test("firmar-pdf: la firma escrita se puede añadir al sello digital", async ({ page }) => {
  const src = await PDFDocument.create();
  src.addPage([400, 500]);
  await page.goto("/es/firmar-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "contrato.pdf", mimeType: "application/pdf", buffer: Buffer.from(await src.save()) });
  await page.getByRole("radio", { name: "Firmar digitalmente" }).check();
  const box = page.locator("[data-seal-image]");
  await box.getByRole("button", { name: "Añadir mi firma al sello" }).click();
  const dialog = page.getByRole("dialog", { name: "Firma" });
  await dialog.getByRole("tab", { name: "Escribir" }).click();
  await dialog.getByLabel("Tu nombre").fill("Ana Pérez");
  await dialog.getByRole("button", { name: "Usar la firma" }).click();
  await expect(box.getByRole("img", { name: "Firma del sello" })).toHaveAttribute("src", /^data:image\/png;base64,/);
  await box.getByRole("button", { name: "Quitar la firma del sello" }).click();
  await expect(box.getByRole("img")).toHaveCount(0);
});
