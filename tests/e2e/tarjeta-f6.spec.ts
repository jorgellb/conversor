import { readFileSync } from "node:fs";

import { PDFArray, PDFDocument, PDFName } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

// crear-tarjeta (A.1, F6-N2, D-232) en Chromium: editor con Konva y exportación en el worker, sin subir fotos ni la lista.

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

async function solidJpeg(page: Page, color: string): Promise<Buffer> {
  const b64 = await page.evaluate(async (c) => {
    const canvas = document.createElement("canvas");
    canvas.width = 800;
    canvas.height = 600;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = c;
    ctx.fillRect(0, 0, 800, 600);
    const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.95));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (const b of bytes) s += String.fromCharCode(b);
    return btoa(s);
  }, color);
  return Buffer.from(b64, "base64");
}

async function downloads(page: Page): Promise<Map<string, Buffer>> {
  const links = page.locator("[data-card-download]");
  await expect(links.first()).toBeVisible({ timeout: 60_000 });
  const out = new Map<string, Buffer>();
  for (let i = 0; i < (await links.count()); i += 1) {
    const [file] = await Promise.all([page.waitForEvent("download"), links.nth(i).click()]);
    out.set(file.suggestedFilename(), readFileSync(await file.path()));
  }
  return out;
}

test("crear-tarjeta: díptica de Navidad con foto, para imprimir en casa y sin subir nada", async ({ page, request }) => {
  expect((await request.get("/es/crear-tarjeta")).headers()["permissions-policy"]).toContain("camera=(self)");
  const sent = watchUploads(page);
  await page.goto("/es/crear-tarjeta");
  await page.getByLabel("Formato").selectOption("diptica");
  await page.getByLabel("Ocasión").selectOption("navidad");
  await page.locator("[data-card-apply]").click();
  await expect(page.locator("[data-card-face]")).toHaveCount(4);
  await page.locator('input[type="file"][multiple]').setInputFiles({ name: "abeto.jpg", mimeType: "image/jpeg", buffer: await solidJpeg(page, "#1f7a3a") });
  await expect(page.getByRole("button", { name: "Poner abeto.jpg en la tarjeta" })).toBeVisible({ timeout: 20_000 });
  await page.locator("[data-card-create]").click();
  const files = await downloads(page);
  const pdf = await PDFDocument.load(files.get("tarjetas.pdf")!);
  expect(pdf.getPageCount()).toBe(2); // exterior e interior de la hoja
  await expect(page.locator("[data-card-notes]")).toContainText("Dobla por las marcas");
  expect(sent).toEqual([]);
});

test("crear-tarjeta: postal con lista de destinatarios para imprenta, con sangrado", async ({ page }) => {
  await page.goto("/es/crear-tarjeta");
  await expect(page.locator("[data-collage-stage]")).toBeVisible({ timeout: 20_000 });
  const csv = "Nombre;Dirección;CP;Ciudad\nAna Núñez;Calle Mayor, 5;28013;Madrid\nLuis Peña;Rúa do Vilar 2;15705;Santiago\n";
  await page.locator('input[type="file"][accept*=".csv"]').setInputFiles({ name: "lista.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.locator("[data-card-recipients]")).toHaveText("2 destinatarios.");
  await page.locator("[data-card-address]").click();
  await expect(page.locator("[data-card-face='1']")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Texto", { exact: true })).toHaveValue("{Nombre}\n{Dirección}\n{CP} {Ciudad}");
  await page.getByLabel("Salida").selectOption("imprenta");
  await page.locator("[data-card-create]").click();
  const files = await downloads(page);
  const pdf = await PDFDocument.load(files.get("tarjeta-imprenta.pdf")!);
  expect(pdf.getPageCount()).toBe(4); // dos destinatarios, frente y reverso
  const trim = pdf.getPage(0).node.lookup(PDFName.of("TrimBox"), PDFArray);
  expect(trim.size()).toBe(4);
  await expect(page.locator("[data-card-notes]")).toContainText("3 mm de sangrado");
});

test("crear-tarjeta: texto en curva con contorno, QR y salida en imagen", async ({ page }) => {
  await page.goto("/es/crear-tarjeta");
  await expect(page.locator("[data-collage-stage]")).toBeVisible({ timeout: 20_000 });
  await page.locator("[data-card-add-qr]").click();
  await page.getByLabel("Contenido del código (enlace o texto)").fill("https://ejemplo.test/tarjeta");
  await page.locator("[data-card-add-text]").click();
  await page.getByLabel("Texto", { exact: true }).fill("Para ti");
  await page.getByLabel("Curva (arco o sonrisa)").fill("0.6");
  await page.getByLabel("Contorno", { exact: true }).check();
  await page.getByLabel("Salida").selectOption("imagen");
  await page.locator("[data-card-create]").click();
  const files = await downloads(page);
  expect([...files.keys()].sort()).toEqual(["tarjeta-frente.jpg", "tarjeta-reverso.jpg", "tarjetas.zip"]);
  const jpg = files.get("tarjeta-frente.jpg")!;
  expect(jpg[0]).toBe(0xff);
  expect(jpg.length).toBeGreaterThan(20_000);
});
