import { expect, test } from "@playwright/test";

// F4, lote A: la página de verificar-firmas-pdf. La validación con pyHanko la prueba pytest (tests/test_firmas.py) con
// la PKI de pruebas de certomancer; la lista de confianza de la UE real, el worker sign.verify en e2e-compose.

test("verificar-firmas-pdf: solo PDF, revocación en línea apagada y contenido sin indexar", async ({ page }) => {
  await page.goto("/es/verificar-firmas-pdf");
  await expect(page.getByRole("heading", { level: 1, name: "Verificar firmas de PDF" })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".pdf");
  await expect(page.getByLabel("Comprobar la revocación en línea (OCSP y CRL)")).not.toBeChecked();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});

test("verify-pdf-signatures en inglés", async ({ page }) => {
  await page.goto("/en/verify-pdf-signatures");
  await expect(page.getByRole("heading", { level: 1, name: "Verify PDF signatures" })).toBeVisible();
  await expect(page.getByLabel("Check revocation online (OCSP and CRL)")).not.toBeChecked();
});
