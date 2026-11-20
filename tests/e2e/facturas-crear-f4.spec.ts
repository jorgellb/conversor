import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// F4, lote E1: crear-factura en el navegador (encendida en la CI con INVOICING_ES_ENABLED y TOOL_CREAR_FACTURA_ENABLED).
// Totales en vivo con recargo e IRPF, validación del NIF y del IBAN, PDF sin subir nada y el emisor recordado. El cálculo
// y el PDF los prueba Vitest (packages/client-tools/test/invoice.test.ts).

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test("crear-factura: totales en vivo, validación y PDF sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/crear-factura");
  await expect(page.getByRole("heading", { level: 1, name: "Crear factura" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Veri*factu");
  const issuer = page.locator("[data-party='issuer']");
  await issuer.getByLabel("Nombre o razón social").fill("Estudio Pérez, S.L.");
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345675");
  const customer = page.locator("[data-party='customer']");
  await customer.getByLabel("Nombre o razón social").fill("Ana García");
  const line = page.locator("[data-line='0']");
  await line.getByLabel("Descripción").fill("Diseño de logotipo");
  await line.getByLabel("Precio sin IVA").fill("450");
  await page.getByRole("button", { name: "Añadir concepto" }).click();
  const second = page.locator("[data-line='1']");
  await second.getByLabel("Descripción").fill("Libro técnico");
  await second.getByLabel("Cantidad").fill("2");
  await second.getByLabel("Precio sin IVA").fill("19,95");
  await second.locator("select").selectOption("4");
  const preview = page.locator("[data-invoice-preview]");
  await expect(preview.locator("[data-total]")).toHaveText("586,00 €");
  await page.getByLabel(/Recargo de equivalencia/).check();
  await page.getByLabel("Retención de IRPF").selectOption("15");
  await expect(preview).toContainText("Recargo 5,2 %");
  await expect(preview.locator("[data-payable]")).toHaveText("536,11 €");
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1333");
  await page.getByRole("button", { name: "Generar el PDF" }).click();
  await expect(page.getByText("Tu NIF, NIE o CIF no es válido.")).toBeVisible();
  await expect(page.getByText("El IBAN no es válido.").first()).toBeVisible();
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345674");
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1332");
  await page.getByRole("button", { name: "Generar el PDF" }).click();
  const link = page.getByRole("link", { name: /Descargar factura-/ });
  await expect(link).toBeVisible();
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(d.suggestedFilename()).toMatch(/^factura-\d{4}-0001\.pdf$/);
  expect(readFileSync(await d.path()).subarray(0, 5).toString()).toBe("%PDF-");
  expect(sent).toEqual([]);
  // El emisor y el número siguiente se recuerdan en este navegador.
  await page.reload();
  await expect(page.locator("[data-party='issuer']").getByLabel("Nombre o razón social")).toHaveValue("Estudio Pérez, S.L.");
  await expect(page.getByLabel("Número de factura")).toHaveValue(/\d{4}\/0002$/);
  await expect(page.locator("[data-party='customer']").getByLabel("Clientes guardados en este navegador")).toBeVisible();
});
