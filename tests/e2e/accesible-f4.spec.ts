import { expect, test } from "@playwright/test";

// F4, lote F: la página de word-a-pdf-accesible. La cadena LibreOffice → veraPDF la prueba pytest
// (tests/test_word_accesible.py); Gotenberg y veraPDF reales, el job e2e-compose de la CI.

test("word-a-pdf-accesible: solo Word, PDF/UA fijo y opciones de A.8 para Word", async ({ page }) => {
  await page.goto("/es/word-a-pdf-accesible");
  await expect(page.getByRole("heading", { level: 1, name: "Word a PDF accesible" })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".doc,.docx,.odt,.rtf");
  await expect(page.getByLabel("Páginas", { exact: true })).toHaveValue("todas");
  await expect(page.getByLabel("Título del documento (si el archivo no tiene)")).toHaveValue("");
  await expect(page.getByLabel("Idioma principal del texto")).toHaveValue("documento");
  // El formato no se elige: siempre PDF/UA. Tampoco salen las opciones de Excel ni de PowerPoint.
  await expect(page.getByLabel("Formato", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Contraseña del documento")).toBeHidden();
  await page.getByText("Opciones adicionales", { exact: true }).click();
  await expect(page.getByLabel("Marcadores desde los títulos")).toBeChecked();
  await expect(page.getByLabel("Exportar campos de formulario")).toBeChecked();
  await expect(page.getByLabel("Calidad de imágenes (%)")).toHaveValue("90");
  await expect(page.getByLabel("Resolución máxima (ppp)")).toHaveValue("300");
  await expect(page.getByLabel("Word: comentarios en el margen")).not.toBeChecked();
  await expect(page.getByLabel("Excel: cada hoja en una sola página")).toHaveCount(0);
  await expect(page.getByLabel("PowerPoint: páginas de notas")).toHaveCount(0);
  // Contenido sin revisar (8.2.5): la página no se indexa todavía.
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});

test("accessible-word-to-pdf en inglés: etiquetas e idiomas", async ({ page }) => {
  await page.goto("/en/accessible-word-to-pdf");
  await expect(page.getByRole("heading", { level: 1, name: "Accessible Word to PDF" })).toBeVisible();
  await expect(page.getByLabel("Main text language")).toHaveValue("documento");
  await expect(page.getByLabel("Main text language").locator("option").first()).toHaveText("The one the document declares");
  await expect(page.getByLabel("Document title (if the file has none)")).toBeVisible();
});
