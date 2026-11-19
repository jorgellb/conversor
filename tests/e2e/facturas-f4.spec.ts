import { expect, test } from "@playwright/test";

// F4, lote D: la página de validar-factura-electronica. La validación con KoSIT y los XSD de Facturae la prueba pytest
// (tests/test_facturas.py); workerutils, el job e2e-compose.

test("validar-factura-electronica: XML, PDF y ZIP, sin opciones y contenido sin indexar", async ({ page }) => {
  await page.goto("/es/validar-factura-electronica");
  await expect(page.getByRole("heading", { level: 1, name: "Validar factura electrónica" })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".xml,.pdf,.zip");
  await expect(page.getByText("Opciones adicionales", { exact: true })).toHaveCount(0);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});

test("validate-e-invoice en inglés", async ({ page }) => {
  await page.goto("/en/validate-e-invoice");
  await expect(page.getByRole("heading", { level: 1, name: "Validate e-invoice" })).toBeVisible();
});
