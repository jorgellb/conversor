import { readFileSync } from "node:fs";

import { expect, test, type Download, type Page } from "@playwright/test";
import { unzipSync } from "fflate";
import UTIF from "utif2";

import { GIF_ANIM, JPEG_GPS, PNG_GPS, TIFF_2P } from "../../packages/client-tools/test/images-f5.fixture";

// Imágenes de F5 (7.11 y A.10) en Chromium: jSquash, resvg y los codificadores propios dentro del Web Worker.
const b64 = (s: string) => Buffer.from(s, "base64");
const latin1 = (b: Uint8Array) => Buffer.from(b).toString("latin1");

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

async function run(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Empezar", exact: true }).click();
  await expect(page.getByRole("region", { name: "Resultado" })).toBeVisible({ timeout: 60_000 });
}

async function download(page: Page, name: string | RegExp): Promise<Buffer> {
  const link = page.getByRole("link", { name }).first();
  const [file]: [Download, void] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return readFileSync(await file.path());
}

/** Dimensiones de la imagen según el decodificador del propio navegador. */
async function decodedSize(page: Page, bytes: Buffer, type: string): Promise<[number, number]> {
  return page.evaluate(async ({ data, mime }) => {
    const bin = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bin], { type: mime }));
    return [bmp.width, bmp.height] as [number, number];
  }, { data: bytes.toString("base64"), mime: type });
}

test("convertir-imagen: de PNG con transparencia a AVIF, WEBP, GIF, BMP, TIFF e ICO sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/convertir-imagen");
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: b64(PNG_GPS) });
  const expected: Record<string, [string, string, (b: Buffer) => boolean]> = {
    avif: ["logo.avif", "image/avif", (b) => latin1(b.subarray(4, 12)) === "ftypavif"],
    webp: ["logo.webp", "image/webp", (b) => latin1(b.subarray(0, 4)) === "RIFF" && latin1(b.subarray(8, 12)) === "WEBP"],
    gif: ["logo.gif", "image/gif", (b) => latin1(b.subarray(0, 6)) === "GIF89a"],
    bmp: ["logo.bmp", "image/bmp", (b) => latin1(b.subarray(0, 2)) === "BM"],
    ico: ["logo.ico", "image/x-icon", (b) => b.readUInt16LE(2) === 1 && b.readUInt16LE(4) === 4],
  };
  for (const [format, [name, mime, check]] of Object.entries(expected)) {
    await page.getByLabel("Convertir a").selectOption(format);
    await run(page);
    const bytes = await download(page, new RegExp(`Descargar · ${name.replace(".", "\\.")}`));
    expect(check(bytes), format).toBe(true);
    if (format !== "ico") expect(await decodedSize(page, bytes, mime)).toEqual([40, 30]);
  }
  await page.getByLabel("Convertir a").selectOption("tiff");
  await run(page);
  const tiff = await download(page, /logo\.tiff/);
  const buf = tiff.buffer.slice(tiff.byteOffset, tiff.byteOffset + tiff.byteLength);
  const [ifd] = UTIF.decode(buf);
  UTIF.decodeImage(buf, ifd);
  expect([ifd.width, ifd.height, ifd.t259]).toEqual([40, 30, [5]]);
  expect(sent).toEqual([]);
});

test("tiff-a-jpg: un JPG por página y ZIP; gif-a-png avisa de la animación", async ({ page }) => {
  await page.goto("/es/tiff-a-jpg");
  await page.locator('input[type="file"]').setInputFiles({ name: "escaneo.tif", mimeType: "image/tiff", buffer: b64(TIFF_2P) });
  await run(page);
  const zip = unzipSync(await download(page, /Descargar todo/));
  expect(Object.keys(zip)).toEqual(["escaneo-p1.jpg", "escaneo-p2.jpg"]);
  expect(await decodedSize(page, Buffer.from(zip["escaneo-p2.jpg"]), "image/jpeg")).toEqual([16, 8]);

  await page.goto("/es/gif-a-png");
  await page.locator('input[type="file"]').setInputFiles({ name: "anim.gif", mimeType: "image/gif", buffer: b64(GIF_ANIM) });
  await run(page);
  await expect(page.getByText("anim.gif: era una animación; se ha convertido solo el primer fotograma.")).toBeVisible();
  expect(await decodedSize(page, await download(page, /anim\.png/), "image/png")).toEqual([10, 10]);
});

test("svg-a-png al doble con texto (fuentes Noto) y svg-a-jpg con ancho personalizado", async ({ page }) => {
  const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><text x="4" y="28" font-size="24" font-family="Helvetica">Año</text></svg>');
  await page.goto("/es/svg-a-png");
  await page.locator('input[type="file"]').setInputFiles({ name: "rotulo.svg", mimeType: "image/svg+xml", buffer: svg });
  await page.getByLabel("Tamaño", { exact: true }).selectOption("2x");
  await run(page);
  const png = await download(page, /rotulo\.png/);
  expect(await decodedSize(page, png, "image/png")).toEqual([240, 80]);
  // Hay texto pintado: píxeles opacos.
  const opaque = await page.evaluate(async (data) => {
    const bin = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bin], { type: "image/png" }));
    const c = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d")!;
    c.drawImage(bmp, 0, 0);
    const d = c.getImageData(0, 0, bmp.width, bmp.height).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 200) n += 1;
    return n;
  }, png.toString("base64"));
  expect(opaque).toBeGreaterThan(300);

  await page.goto("/es/svg-a-jpg");
  await page.locator('input[type="file"]').setInputFiles({ name: "rotulo.svg", mimeType: "image/svg+xml", buffer: svg });
  await page.getByLabel("Tamaño", { exact: true }).selectOption("ancho");
  await page.getByLabel("Ancho (px, se mantiene la proporción)").fill("600");
  await run(page);
  expect(await decodedSize(page, await download(page, /rotulo\.jpg/), "image/jpeg")).toEqual([600, 200]);
});

test("crear-favicon desde SVG: código HTML para copiar y ZIP con todo", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/crear-favicon");
  const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5" fill="#0a7"/></svg>');
  await page.locator('input[type="file"]').setInputFiles({ name: "marca.svg", mimeType: "image/svg+xml", buffer: svg });
  await page.getByLabel("Nombre del sitio (para el manifiesto)").fill("Producto Demo");
  await run(page);
  await expect(page.locator("code").first()).toContainText('<link rel="icon" href="/icon.svg" type="image/svg+xml">');
  const zip = unzipSync(await download(page, /Descargar todo/));
  expect(Object.keys(zip).sort()).toEqual(["apple-touch-icon.png", "codigo-html.txt", "favicon.ico", "icon-192.png", "icon-512.png",
    "icon-mask.png", "icon.svg", "manifest.webmanifest"]);
  expect(JSON.parse(Buffer.from(zip["manifest.webmanifest"]).toString()).name).toBe("Producto Demo");
  expect(await decodedSize(page, Buffer.from(zip["apple-touch-icon.png"]), "image/png")).toEqual([180, 180]);
  expect(await decodedSize(page, Buffer.from(zip["favicon.ico"]), "image/x-icon")).toEqual([48, 48]);
  expect(sent).toEqual([]);
});

test("quitar-metadatos-foto e imagen-a-base64", async ({ page }) => {
  await page.goto("/es/quitar-metadatos-foto");
  await page.locator('input[type="file"]').setInputFiles({ name: "viaje.jpg", mimeType: "image/jpeg", buffer: b64(JPEG_GPS) });
  await run(page);
  await expect(page.getByText(/^Quitado: EXIF, ubicación GPS, XMP, comentarios/)).toBeVisible();
  const clean = await download(page, /viaje-sin-metadatos\.jpg/);
  for (const secret of ["Camara de prueba", "Autor Demo", "comentario privado", "+40.4168"]) expect(latin1(clean)).not.toContain(secret);
  // Sigue siendo la misma foto, en vertical por la orientación conservada.
  expect(await decodedSize(page, clean, "image/jpeg")).toEqual([48, 64]);

  await page.goto("/en/image-to-base64");
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: b64(PNG_GPS) });
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.locator("code").first()).toHaveText(`data:image/png;base64,${PNG_GPS}`, { timeout: 30_000 });
});
