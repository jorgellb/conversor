import { expect, test } from "@playwright/test";

// F3, lote D: la página de pdf-a-audio (la voz real con espeak-ng y Kokoro la prueba pytest en tests/test_pdf_audio.py,
// y el proyecto «servidor», con la pila completa).

test("pdf-a-audio: solo PDF, opciones de la voz, adicionales y límite de caracteres por plan", async ({ page }) => {
  await page.goto("/es/pdf-a-audio");
  await expect(page.getByRole("heading", { level: 1, name: "PDF a audio" })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".pdf");
  await expect(page.getByLabel("Páginas", { exact: true })).toHaveValue("todas");
  await expect(page.getByLabel("Idioma del texto")).toHaveValue("auto");
  await expect(page.getByLabel("Idioma del texto").locator("option")).toHaveText(["Detectar el idioma", "Español", "Inglés"]);
  await expect(page.getByLabel("Voz", { exact: true })).toHaveValue("predeterminada");
  await expect(page.getByLabel("Velocidad (1 = normal; 2 = el doble de rápido)")).toHaveValue("1");
  await expect(page.getByLabel("Calidad MP3")).toHaveValue("128");
  await expect(page.getByLabel("Pausa entre párrafos (s)")).toBeHidden();
  await page.getByText("Opciones adicionales", { exact: true }).click();
  await expect(page.getByLabel("Pausa entre párrafos (s)")).toHaveValue("0.6");
  await expect(page.getByLabel("Saltar cabeceras, pies y números de página")).toBeChecked();
  await expect(page.getByLabel(/^Leer las páginas escaneadas/)).toBeChecked();
  const row = page.getByRole("row", { name: /Caracteres leídos por tarea/ });
  await expect(row.getByRole("cell")).toHaveText(["Necesita cuenta", "20.000", "300.000"]);
  // Contenido sin revisar (8.2.5): la página no se indexa todavía.
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});

test("pdf-to-audio en inglés: etiquetas, voces y límite con separador inglés", async ({ page }) => {
  await page.goto("/en/pdf-to-audio");
  await expect(page.getByRole("heading", { level: 1, name: "PDF to audio" })).toBeVisible();
  await expect(page.getByLabel("Text language")).toHaveValue("auto");
  await expect(page.getByLabel("Voice", { exact: true }).locator("option")).toHaveText(["The recommended one", "Female voice", "Male voice"]);
  await expect(page.getByLabel("MP3 quality").locator("option")).toHaveText(["128 kbps", "192 kbps"]);
  const row = page.getByRole("row", { name: /Characters read per task/ });
  await expect(row.getByRole("cell")).toHaveText(["Needs an account", "20,000", "300,000"]);
});
