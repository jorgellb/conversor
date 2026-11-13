import { expect, test } from "@playwright/test";

// F5, lote C: las páginas de las herramientas de imagen en el servidor (el proceso real lo prueban pytest y el proyecto
// «servidor» con la pila completa).

test("heic-a-jpg y heic-a-png apagadas explican cómo pasar a JPEG; raw-a-jpg acepta RAW de cámara", async ({ page }) => {
  for (const slug of ["heic-a-jpg", "heic-a-png"]) {
    await page.goto(`/es/${slug}`);
    await expect(page.getByRole("heading", { name: "Cómo pasar fotos HEIC a JPEG" })).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  }
  await page.goto("/es/raw-a-jpg");
  await expect(page.locator('input[type="file"]')).toHaveAttribute("accept", ".cr2,.nef,.arw,.dng");
  await expect(page.getByText("Formatos admitidos: CR2, NEF, ARW, DNG")).toBeVisible();
  await expect(page.getByLabel("Balance de blancos")).toHaveValue("camara");
});

test("quitar-fondo, psd-a-png y png-a-svg muestran sus opciones", async ({ page }) => {
  await page.goto("/es/quitar-fondo");
  await expect(page.getByLabel("Formato")).toHaveValue("png");
  await expect(page.getByLabel("Color del fondo")).toHaveCount(0);
  await page.getByLabel("Fondo", { exact: true }).selectOption("color");
  await expect(page.getByLabel("Color del fondo")).toBeVisible();
  await page.goto("/en/psd-to-png");
  await expect(page.getByLabel("What to export")).toHaveValue("imagen");
  await page.goto("/es/png-a-svg");
  await expect(page.getByLabel("Detalle")).toHaveValue("medio");
});
