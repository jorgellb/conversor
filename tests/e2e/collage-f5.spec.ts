import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { inflateSync } from "node:zlib";

import { PDFArray, PDFDocument, PDFName, PDFRawStream, PDFRef } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

import { insertExif } from "../../packages/client-tools/src/exif";

// crear-collage (A.1): editor con Konva en la página y exportación en el worker, sin subir las fotos.

const W = 640;
const H = 480;

/** Vídeo Y4M para la cámara simulada de Chromium: un fondo verde liso. */
function writeY4m(file: string): void {
  const luma = Buffer.alloc(W * H, 150);
  const u = Buffer.alloc((W / 2) * (H / 2), 54);
  const v = Buffer.alloc((W / 2) * (H / 2), 34);
  const frame = Buffer.concat([Buffer.from("FRAME\n"), luma, u, v]);
  writeFileSync(file, Buffer.concat([Buffer.from(`YUV4MPEG2 W${W} H${H} F10:1 Ip A1:1 C420jpeg\n`), frame, frame, frame]));
}

const dir = path.join(os.tmpdir(), "conversor-e2e");
mkdirSync(dir, { recursive: true });
const video = path.join(dir, "collage.y4m");
writeY4m(video);

test.use({
  launchOptions: {
    ...(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {}),
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${video}`],
  },
});

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

/** JPEG de un color liso (4:3) hecho con el lienzo del navegador. */
async function solidJpeg(page: Page, color: string): Promise<Buffer> {
  const b64 = await page.evaluate(async (c) => {
    const canvas = document.createElement("canvas");
    canvas.width = 400;
    canvas.height = 300;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = c;
    ctx.fillRect(0, 0, 400, 300);
    const blob = await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.95));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (const b of bytes) s += String.fromCharCode(b);
    return btoa(s);
  }, color);
  return Buffer.from(b64, "base64");
}

/** Color del píxel (x, y) de una imagen PNG o JPEG, decodificada en el navegador. */
async function pixelAt(page: Page, bytes: Buffer, x: number, y: number): Promise<number[]> {
  return page.evaluate(async ({ data, x, y }) => {
    const raw = Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([raw]));
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(bitmap, 0, 0);
    return Array.from(ctx.getImageData(x, y, 1, 1).data.slice(0, 3));
  }, { data: bytes.toString("base64"), x, y });
}

async function open(page: Page) {
  await page.goto("/es/crear-collage");
  await expect(page.locator("[data-collage-stage] canvas").first()).toBeVisible();
}

test("crear-collage: dos fotos, intercambio arrastrando y PNG a 150 ppp sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await open(page);
  const red = await solidJpeg(page, "#E01010");
  const blue = await solidJpeg(page, "#1030E0");
  await page.locator("[data-collage-files]").setInputFiles([
    { name: "roja.jpg", mimeType: "image/jpeg", buffer: red },
    { name: "azul.jpg", mimeType: "image/jpeg", buffer: blue },
  ]);
  await expect(page.locator("[data-collage-photo='azul.jpg']")).toBeVisible();
  // Dos huecos (empieza con cuatro y se recoloca al quitar los vacíos).
  await page.getByLabel("Huecos para fotos").fill("2");
  // A4 vertical, margen 10 y separación 4: una columna con dos celdas (roja arriba, azul abajo).
  const canvas = page.locator("[data-collage-stage] canvas").first();
  const box = (await canvas.boundingBox())!;
  const k = box.width / 210;
  const top = { x: box.x + 105 * k, y: box.y + 78 * k };
  const bottom = { x: box.x + 105 * k, y: box.y + 219 * k };
  await page.mouse.move(bottom.x, bottom.y);
  await page.mouse.down();
  await page.mouse.move(top.x, top.y, { steps: 12 });
  await page.mouse.up();
  await expect(page.locator("[data-collage-selection], select").filter({ hasText: "Celda 1" }).first()).toHaveValue("c0");

  await page.getByLabel("Formato").selectOption("png");
  await page.getByLabel("Resolución de exportación").selectOption("150");
  await page.locator("[data-collage-create]").click();
  const link = page.getByRole("link", { name: "Descargar collage.png" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const png = readFileSync(await download.path());
  // 150 ppp: 1240 px de ancho; la azul está ahora arriba y la roja abajo.
  const s = 1240 / 210;
  const [r1, , b1] = await pixelAt(page, png, Math.round(105 * s), Math.round(78 * s));
  const [r2, , b2] = await pixelAt(page, png, Math.round(105 * s), Math.round(219 * s));
  expect(b1).toBeGreaterThan(150);
  expect(r1).toBeLessThan(100);
  expect(r2).toBeGreaterThan(150);
  expect(b2).toBeLessThan(100);
  expect(sent).toEqual([]);
});

test("crear-collage: PDF con la foto sin recomprimir, texto y sticker", async ({ page }) => {
  const sent = watchUploads(page);
  await open(page);
  const jpeg = await solidJpeg(page, "#20A040");
  await page.locator("[data-collage-files]").setInputFiles({ name: "verde.jpg", mimeType: "image/jpeg", buffer: jpeg });
  await expect(page.locator("[data-collage-photo='verde.jpg']")).toBeVisible();
  await page.getByRole("button", { name: "Añadir texto" }).click();
  await page.getByLabel("Texto", { exact: true }).fill("Verano en Cádiz");
  await page.getByRole("button", { name: "Añadir sticker: Estrella" }).click();
  await page.getByLabel("Orientación").selectOption("horizontal");
  await page.locator("[data-collage-create]").click();
  const link = page.getByRole("link", { name: "Descargar collage.pdf" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const pdf = await PDFDocument.load(readFileSync(await download.path()));
  expect(pdf.getPageCount()).toBe(1);
  const { width, height } = pdf.getPage(0).getSize();
  expect(Math.round(width)).toBe(842);
  expect(Math.round(height)).toBe(595);
  const images: Uint8Array[] = [];
  for (const [, obj] of pdf.context.enumerateIndirectObjects()) {
    if (obj instanceof PDFRawStream && obj.dict.get(PDFName.of("Subtype"))?.toString() === "/Image") images.push(obj.contents);
  }
  expect(images).toHaveLength(1);
  expect(Buffer.from(images[0]).equals(jpeg)).toBe(true);
  expect(sent).toEqual([]);
});

test("crear-collage: foto con la cámara del dispositivo", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Hacer una foto" }).click();
  const dialog = page.getByRole("dialog", { name: "Cámara" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Hacer la foto" })).toBeEnabled({ timeout: 15_000 });
  await dialog.getByRole("button", { name: "Hacer la foto" }).click();
  await expect(page.locator("[data-collage-photo='camara-1.jpg']")).toBeVisible();
  await expect(dialog.getByText("Foto 1 añadida.")).toBeVisible();
  await dialog.getByRole("button", { name: "Cerrar la cámara" }).click();
  await expect(dialog).toBeHidden();
  // La cámara se ha apagado al cerrar.
  expect(await page.evaluate(() => document.querySelectorAll("video").length)).toBe(0);
});

test("crear-collage: la cámara solo se permite en su página", async ({ request }) => {
  expect((await request.get("/es/crear-collage")).headers()["permissions-policy"]).toContain("camera=(self)");
  expect((await request.get("/en/collage-maker")).headers()["permissions-policy"]).toContain("camera=(self)");
  expect((await request.get("/es/unir-pdf")).headers()["permissions-policy"]).toContain("camera=()");
});

/** TIFF big-endian con DateTimeOriginal (subIFD EXIF), para insertarlo en un JPEG. */
function exifWithDate(date: string): Uint8Array {
  const b = new Uint8Array(96);
  const v = new DataView(b.buffer);
  b.set([0x4d, 0x4d, 0, 0x2a]);
  v.setUint32(4, 8);
  v.setUint16(8, 1);
  v.setUint16(10, 0x8769); v.setUint16(12, 4); v.setUint32(14, 1); v.setUint32(18, 26);
  v.setUint16(26, 1);
  v.setUint16(28, 0x9003); v.setUint16(30, 2); v.setUint32(32, 20); v.setUint32(36, 44);
  b.set(new TextEncoder().encode(date), 44);
  return b;
}

function imageStreams(pdf: PDFDocument): Uint8Array[] {
  const found: Uint8Array[] = [];
  for (const [, obj] of pdf.context.enumerateIndirectObjects()) {
    if (obj instanceof PDFRawStream && obj.dict.get(PDFName.of("Subtype"))?.toString() === "/Image") found.push(obj.contents);
  }
  return found;
}

/** Operadores de la página ya descomprimidos. */
function pageOperators(pdf: PDFDocument, index: number): string {
  const contents = pdf.getPage(index).node.get(PDFName.of("Contents"));
  const refs = contents instanceof PDFArray ? contents.asArray() : [contents];
  return refs.map((ref) => {
    const stream = pdf.context.lookup(ref as PDFRef) as PDFRawStream;
    return inflateSync(Buffer.from(stream.contents)).toString("latin1");
  }).join("\n");
}

test("crear-collage: hoja de fotos de carné a tamaño real con una sola foto y marcas de corte", async ({ page }) => {
  const sent = watchUploads(page);
  await open(page);
  await page.getByLabel("Tipo de plantilla").selectOption("tamano");
  await expect(page.getByLabel("Medida")).toHaveValue("carne-ue");
  const jpeg = await solidJpeg(page, "#D02020");
  await page.locator("[data-collage-files]").setInputFiles({ name: "carne.jpg", mimeType: "image/jpeg", buffer: jpeg });
  await expect(page.locator("[data-collage-photo='carne.jpg']")).toBeVisible();
  await expect(page.locator("[data-collage-capacity]")).toHaveText("Caben 20 en la página.");
  await expect(page.getByLabel("Marcas de corte")).toBeChecked();
  await expect(page.locator("[data-collage-print-note]")).toBeVisible();
  await page.locator("[data-collage-create]").click();
  const link = page.getByRole("link", { name: "Descargar collage.pdf" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const pdf = await PDFDocument.load(readFileSync(await download.path()));
  // Una sola copia de la foto (con sus bytes) dibujada 20 veces, más los trazos de las marcas de corte.
  const images = imageStreams(pdf);
  expect(images).toHaveLength(1);
  expect(Buffer.from(images[0]).equals(jpeg)).toBe(true);
  const ops = pageOperators(pdf, 0);
  expect(ops.match(/\bDo\b/g)).toHaveLength(20);
  expect(ops).toMatch(/\bS\b/);
  // DNI y pasaporte: 26 × 32 mm, 42 por A4.
  await page.getByLabel("Medida").selectOption("dni");
  await expect(page.locator("[data-collage-capacity]")).toHaveText("Caben 42 en la página.");
  expect(sent).toEqual([]);
});

test("crear-collage: documentación fotográfica con la fecha EXIF, pie propio y dos fotos por página", async ({ page }) => {
  const sent = watchUploads(page);
  await open(page);
  await page.getByLabel("Tipo de plantilla").selectOption("documentacion");
  await page.getByLabel("Fotos por página").selectOption("2");
  await page.getByLabel("Encabezado de cada página").fill("Informe de obra");
  await page.getByLabel("Números de página").check();
  const base = await solidJpeg(page, "#2060C0");
  const dated = Buffer.from(insertExif(new Uint8Array(base), exifWithDate("2026:03:12 10:45:00")));
  await page.locator("[data-collage-files]").setInputFiles([
    { name: "obra-1.jpg", mimeType: "image/jpeg", buffer: dated },
    { name: "obra-2.jpg", mimeType: "image/jpeg", buffer: base },
    { name: "obra-3.jpg", mimeType: "image/jpeg", buffer: base },
  ]);
  await expect(page.locator("[data-collage-photo='obra-3.jpg']")).toBeVisible();
  // El navegador lee la fecha de captura del EXIF.
  await expect(page.locator("[data-collage-photo='obra-1.jpg']")).toHaveAttribute("title", "obra-1.jpg · 12/03/2026 10:45");
  await expect(page.locator("[data-collage-photo='obra-2.jpg']")).toHaveAttribute("title", "obra-2.jpg");
  await expect(page.getByRole("toolbar", { name: "Páginas" }).getByRole("button", { name: /^Página \d+$/ })).toHaveCount(2);
  await page.getByRole("button", { name: "Página 1", exact: true }).click();
  await page.getByLabel("Elemento", { exact: true }).selectOption("c0");
  await page.getByLabel("Pie de foto").fill("Fachada norte");
  await page.locator("[data-collage-create]").click();
  const link = page.getByRole("link", { name: "Descargar collage.pdf" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const pdf = await PDFDocument.load(readFileSync(await download.path()));
  expect(pdf.getPageCount()).toBe(2);
  // Las fotos van tal cual (la que tiene EXIF, con él).
  const images = imageStreams(pdf).map((b) => Buffer.from(b));
  expect(images.some((b) => b.equals(dated))).toBe(true);
  expect(images.some((b) => b.equals(base))).toBe(true);
  // Texto de pies, encabezado y número de página en cada hoja.
  for (const i of [0, 1]) expect(pageOperators(pdf, i)).toMatch(/\bTj\b|\bTJ\b/);
  expect(sent).toEqual([]);
});
