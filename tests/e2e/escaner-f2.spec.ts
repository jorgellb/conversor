import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { PDFDocument } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

// escaner-pdf (A.4) con la cámara simulada de Chromium: un vídeo Y4M con un papel torcido sobre una mesa oscura.
const W = 640;
const H = 480;
// Papel vertical: unos 250 px de ancho por 390 de alto (proporción ≈ 1,56).
const DOC = [{ x: 200, y: 40 }, { x: 450, y: 60 }, { x: 440, y: 450 }, { x: 190, y: 430 }];

function inside(x: number, y: number): boolean {
  let hit = false;
  for (let i = 0, j = DOC.length - 1; i < DOC.length; j = i++) {
    const a = DOC[i];
    const b = DOC[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

function writeY4m(file: string): void {
  const luma = Buffer.alloc(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let v = 40;
      if (inside(x, y)) {
        v = 230;
        if (y > 120 && y < 380 && (y - 120) % 28 < 6 && x > 230 && x < 410) v = 35;
      }
      luma[y * W + x] = v;
    }
  }
  const chroma = Buffer.alloc((W / 2) * (H / 2), 128);
  const frame = Buffer.concat([Buffer.from("FRAME\n"), luma, chroma, chroma]);
  writeFileSync(file, Buffer.concat([Buffer.from(`YUV4MPEG2 W${W} H${H} F10:1 Ip A1:1 C420jpeg\n`), frame, frame, frame]));
}

const dir = path.join(os.tmpdir(), "conversor-e2e");
mkdirSync(dir, { recursive: true });
const video = path.join(dir, "documento.y4m");
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

test("escaner-pdf: la cámara solo se permite en su página", async ({ request }) => {
  expect((await request.get("/es/escaner-pdf")).headers()["permissions-policy"]).toContain("camera=(self)");
  expect((await request.get("/en/pdf-scanner")).headers()["permissions-policy"]).toContain("camera=(self)");
  expect((await request.get("/es/unir-pdf")).headers()["permissions-policy"]).toContain("camera=()");
});

test("escaner-pdf: detecta el papel en vivo, captura, añade una foto, gira y crea el PDF sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/escaner-pdf");
  const logs: string[] = [];
  page.on("console", (m) => logs.push(`${m.type()}: ${m.text()}`));
  page.on("pageerror", (e) => logs.push(`pageerror: ${e.message}`));
  await page.getByRole("button", { name: "Abrir la cámara" }).click();
  try {
    await expect(page.locator("[data-detection]")).toHaveAttribute("data-detection", "1", { timeout: 60_000 });
  } catch (err) {
    const detail = await page.locator("[data-detection]").getAttribute("data-detect-error").catch(() => null);
    const size = await page.locator("video").evaluate((v: HTMLVideoElement) => `${v.videoWidth}x${v.videoHeight} ${v.readyState}`).catch(() => "?");
    throw new Error(`Sin detección. Error: ${detail}; vídeo: ${size}; consola: ${logs.slice(-10).join(" | ")}`, { cause: err });
  }
  await expect(page.getByText("Documento detectado: encuádralo y captura.")).toBeVisible();
  await page.getByRole("button", { name: "Capturar página" }).click();
  await expect(page.locator("[data-scanner-status]")).toHaveText("Página 1 añadida.", { timeout: 30_000 });
  await page.getByRole("button", { name: "Cerrar la cámara" }).click();

  // Una foto de la galería sin documento reconocible entra entera.
  const photo = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 300;
    c.height = 200;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#808080";
    ctx.fillRect(0, 0, 300, 200);
    return c.toDataURL("image/png").split(",")[1];
  });
  await page.locator('input[type="file"]').setInputFiles({ name: "foto.png", mimeType: "image/png", buffer: Buffer.from(photo, "base64") });
  await expect(page.locator("[data-scanner-status]")).toHaveText("Página 2 añadida con la foto entera (no se encontró el borde del documento).");
  const pages = page.getByRole("region", { name: "Páginas" }).getByRole("listitem");
  await expect(pages).toHaveCount(2);
  const before = await pages.nth(1).locator("img").evaluate((img: HTMLImageElement) => img.naturalWidth / img.naturalHeight);
  await page.getByRole("button", { name: "Girar la página 2" }).click();
  await expect.poll(() => pages.nth(1).locator("img").evaluate((img: HTMLImageElement) => img.naturalWidth / img.naturalHeight)).toBeCloseTo(1 / before, 2);

  await page.getByRole("button", { name: "Crear PDF (2 páginas)" }).click();
  const link = page.getByRole("link", { name: "Descargar PDF" });
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const pdf = await PDFDocument.load(readFileSync(await download.path()));
  expect(pdf.getPageCount()).toBe(2);
  const first = pdf.getPage(0).getSize();
  expect(Math.round(Math.max(first.width, first.height))).toBe(842);  // automático: lado largo de un A4
  expect(first.height / first.width).toBeGreaterThan(1.45);  // el papel enderezado conserva su proporción vertical
  expect(first.height / first.width).toBeLessThan(1.7);
  expect(sent).toEqual([]);
});
