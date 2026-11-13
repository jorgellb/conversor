import { readFileSync } from "node:fs";

import { expect, test, type Download, type Page } from "@playwright/test";

import { PNG_GPS } from "../../packages/client-tools/test/images-f5.fixture";

// convertir-archivo (7.22): el tipo se detecta por los bytes en el navegador y solo se ofrecen las salidas posibles; la
// conversión elegida se hace en la misma página (?de=…&a=…), con el formato fijado y sin volver a elegir el archivo.
const b64 = (s: string) => Buffer.from(s, "base64");

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test("un PNG con extensión .jpg: se detecta por los bytes y se convierte a ICO aquí mismo, sin subirlo", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/convertir-archivo");
  await expect(page.locator('meta[name="robots"]')).toHaveCount(0);
  await page.locator("[data-converter-files]").setInputFiles({ name: "logo.jpg", mimeType: "image/jpeg", buffer: b64(PNG_GPS) });
  await expect(page.locator("[data-converter-kind]")).toHaveText("Es un archivo PNG.");
  await expect(page.getByText("logo.jpg: la extensión dice JPG, pero por dentro es PNG.")).toBeVisible();
  for (const to of ["pdf", "jpg", "webp", "avif", "ico", "bmp", "svg", "base64"]) await expect(page.locator(`[data-converter-to="${to}"]`)).toBeVisible();
  await expect(page.locator('[data-converter-to="png"]')).toHaveCount(0);
  // png-a-pdf es híbrida (los archivos grandes van al servidor); convertir-imagen, solo del navegador.
  await expect(page.locator('[data-converter-to="pdf"]')).toContainText("navegador o servidor");
  await expect(page.locator('[data-converter-to="ico"]')).not.toContainText("servidor");
  await page.locator('[data-converter-to="ico"]').click();
  await expect(page).toHaveURL(/\/es\/convertir-archivo\?de=png&a=ico$/);
  await expect(page.getByRole("heading", { name: "Convertir PNG a ICO" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  // El archivo ya está puesto y el formato, fijado (no se puede cambiar a otro aquí).
  await expect(page.getByText("logo.jpg")).toBeVisible();
  await expect(page.getByLabel("Convertir a")).toHaveCount(0);
  await page.getByRole("button", { name: "Empezar", exact: true }).click();
  await expect(page.getByRole("region", { name: "Resultado" })).toBeVisible({ timeout: 60_000 });
  const link = page.getByRole("link", { name: /logo\.ico/ }).first();
  const [file]: [Download, void] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const ico = readFileSync(await file.path());
  expect([ico.readUInt16LE(0), ico.readUInt16LE(2)]).toEqual([0, 1]);
  expect(sent).toEqual([]);
});

test("un enlace compartido con la conversión abre su herramienta, sin indexar; uno que no existe vuelve al conversor", async ({ page, request }) => {
  await page.goto("/en/file-converter?de=bmp&a=ico");
  await expect(page.getByRole("heading", { name: "Convert BMP to ICO" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  await expect(page.getByText("Done in your browser")).toBeVisible();
  await page.getByRole("link", { name: "Choose another conversion" }).click();
  await expect(page).toHaveURL(/\/en\/file-converter$/);
  await page.goto("/es/convertir-archivo?de=png&a=mp3");
  await expect(page.getByRole("heading", { name: "Convertir archivo" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  // Sin conversión en la URL (utm_… y demás) es la página del conversor, indexable y con su canonical.
  await page.goto("/es/convertir-archivo?utm_source=prueba");
  await expect(page.locator('meta[name="robots"]')).toHaveCount(0);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/es\/convertir-archivo$/);
  const sitemap = await (await request.get("/sitemap/es.xml")).text();
  expect(sitemap).toContain("/es/convertir-archivo</loc>");
  expect(sitemap).not.toContain("?de=");
});

test("un audio ofrece MP3, WAV y la transcripción en el servidor; lo desconocido y los tipos mezclados se explican", async ({ page }) => {
  await page.goto("/es/convertir-archivo");
  const ogg = Buffer.concat([Buffer.from("OggS\x00\x02", "latin1"), Buffer.alloc(22), Buffer.from("\x01vorbis", "latin1"), Buffer.alloc(40)]);
  await page.locator("[data-converter-files]").setInputFiles({ name: "nota.ogg", mimeType: "audio/ogg", buffer: ogg });
  await expect(page.locator("[data-converter-kind]")).toHaveText("Es un archivo OGG.");
  await expect(page.locator('[data-converter-to="mp3"]')).toContainText("servidor");
  for (const to of ["wav", "txt", "docx", "srt"]) await expect(page.locator(`[data-converter-to="${to}"]`)).toBeVisible();
  await page.locator("[data-converter-files]").setInputFiles({ name: "datos.bin", mimeType: "application/octet-stream", buffer: Buffer.from(Array.from({ length: 512 }, (_, i) => i % 256)) });
  await expect(page.getByText("No reconocemos este tipo de archivo.")).toBeVisible();
  await page.locator("[data-converter-files]").setInputFiles([
    { name: "nota.ogg", mimeType: "audio/ogg", buffer: ogg },
    { name: "logo.png", mimeType: "image/png", buffer: b64(PNG_GPS) },
  ]);
  await expect(page.getByText("Los archivos son de tipos distintos (OGG, PNG): conviértelos por separado.")).toBeVisible();
});

test("conversor-pdf también mira los bytes: un PNG con extensión .jpg ofrece «PNG a PDF», no «JPG a PDF»", async ({ page }) => {
  await page.goto("/es/conversor-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.jpg", mimeType: "image/jpeg", buffer: b64(PNG_GPS) });
  await expect(page.getByRole("button", { name: "PNG a PDF" })).toBeVisible();
  await expect(page.getByRole("button", { name: "JPG a PDF" })).toHaveCount(0);
});
