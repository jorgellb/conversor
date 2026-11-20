import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// mermaid-a-svg y mermaid-a-png (7.13, F6-N, D-231) en Chromium: el diagrama se dibuja y se exporta sin subir nada.

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`));
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().startsWith("CSP")) throw new Error(m.text());
  });
});

async function download(page: Page, name: RegExp): Promise<Buffer> {
  const link = page.locator("[data-mermaid-download]");
  await expect(link).toBeVisible({ timeout: 30_000 });
  await expect(link).toHaveText(name);
  const [file] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return readFileSync(await file.path());
}

test("mermaid-a-png: el ejemplo se dibuja y sale un PNG a 2× sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/mermaid-a-png");
  await page.evaluate(() => localStorage.removeItem("mermaid-borrador"));
  await expect(page.locator("[data-mermaid-preview]")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Descargar PNG" }).click();
  const png = await download(page, /^Descargar diagrama\.png$/);
  expect(png.subarray(1, 4).toString()).toBe("PNG");
  const width = png.readUInt32BE(16);
  const height = png.readUInt32BE(20);
  expect(width).toBeGreaterThan(300);
  expect(height).toBeGreaterThan(300);
  expect(png.length).toBeGreaterThan(10_000); // con formas y texto, no un lienzo vacío
  expect(sent).toEqual([]);
});

test("mermaid-a-svg: un error de sintaxis se señala y, corregido, el SVG lleva el texto", async ({ page }) => {
  await page.goto("/es/mermaid-a-svg");
  const editor = page.locator("[data-mermaid-code]");
  await editor.fill("flowchart LR\n  A[Año nuevo] --> B[Canción]\n  B --> ");
  await expect(page.locator("[data-mermaid-problem]")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Descargar SVG" })).toBeDisabled();
  await editor.fill("flowchart LR\n  A[Año nuevo] --> B[Canción]");
  await expect(page.locator("[data-mermaid-problem]")).toHaveCount(0, { timeout: 30_000 });
  await page.getByLabel("Tema").selectOption("dark");
  await page.getByRole("button", { name: "Descargar SVG" }).click();
  const svg = (await download(page, /^Descargar diagrama\.svg$/)).toString("utf-8");
  expect(svg.startsWith("<?xml")).toBe(true);
  const text = svg.replace(/<[^>]+>/g, ""); // Mermaid pone cada palabra en su <tspan>
  expect(text).toContain("Año nuevo");
  expect(text).toContain("Canción");
  expect(svg).toContain('fill="#1f2020"'); // fondo del tema oscuro
  expect(svg).not.toContain("<foreignObject");
  expect(svg).not.toMatch(/<script/i);
});

test("mermaid-a-svg: abre el bloque mermaid de un Markdown y recuerda el borrador", async ({ page }) => {
  await page.goto("/es/mermaid-a-svg");
  const md = "# Notas\n\nTexto.\n\n```mermaid\nsequenceDiagram\n  Ana->>Luis: Hola\n```\n";
  await page.locator('input[type="file"]').setInputFiles({ name: "notas.md", mimeType: "text/markdown", buffer: Buffer.from(md) });
  await expect(page.locator("[data-mermaid-code]")).toHaveValue("sequenceDiagram\n  Ana->>Luis: Hola");
  await expect(page.getByLabel("Nombre del archivo")).toHaveValue("notas");
  await expect(page.locator("[data-mermaid-preview]")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  await page.reload();
  await expect(page.locator("[data-mermaid-code]")).toHaveValue("sequenceDiagram\n  Ana->>Luis: Hola");
});
