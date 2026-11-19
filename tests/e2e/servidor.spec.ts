import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// Muestras generadas con scripts/fixtures/generate.py (Pillow, pikepdf, FFmpeg y LibreOffice si está). En la CI las
// genera antes el job e2e-compose (E2E_FIXTURES); si no, se usa el Python de .venv, que tiene esas dependencias.
const FIXTURES = process.env.E2E_FIXTURES ?? path.join(tmpdir(), "conversor-e2e");
const PYTHON = process.env.PYTHON ?? (existsSync(".venv/bin/python") ? ".venv/bin/python" : "python3");
// La primera conversión arranca LibreOffice en frío en Gotenberg: el tiempo de la prueba cubre la espera del enlace (180 s).
test.describe.configure({ timeout: 240_000 });
test.beforeAll(() => {
  if (!existsSync(path.join(FIXTURES, "texto.pdf"))) {
    execFileSync(PYTHON, ["-c", `import sys; sys.path.insert(0, "scripts/fixtures"); from generate import generate; from pathlib import Path; generate(Path(${JSON.stringify(FIXTURES)}))`], { stdio: "inherit" });
  }
});

/** Enlace de confirmación del correo que recibe Mailpit (puede tardar unos segundos en llegar). */
async function verificationLink(page: Page, email: string): Promise<string> {
  let id = "";
  await expect.poll(async () => {
    const mail = await (await page.request.get(`http://localhost:8025/api/v1/search?query=to:${encodeURIComponent(email)}`)).json();
    id = mail.messages?.[0]?.ID ?? "";
    return id;
  }, { timeout: 30_000 }).not.toBe("");
  const message = await (await page.request.get(`http://localhost:8025/api/v1/message/${id}`)).json();
  return /https?:\/\/\S+/.exec(message.Text)![0];
}

async function runServerTool(page: Page, slug: string, files: string[]) {
  await page.goto(`/es/${slug}`);
  await page.locator('input[type="file"]').setInputFiles(files.map((f) => path.join(FIXTURES, f)));
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 180_000 });
  const href = await link.getAttribute("href");
  expect(href).toMatch(/\/d\/[0-9a-f-]{36}\/.+\?t=/);
  const res = await page.request.get(href!);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-disposition"]).toContain("attachment");
  expect(res.headers()["content-security-policy"]).toBe("default-src 'none'; sandbox");
  return res.body();
}

test("comprimir-pdf: subida por tus, trabajo y descarga firmada", async ({ page }) => {
  const body = await runServerTool(page, "comprimir-pdf", ["fotos.pdf"]);
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  expect(body.length).toBeLessThan(readFileSync(path.join(FIXTURES, "fotos.pdf")).length);
});

test("ogg-a-mp3", async ({ page }) => {
  const body = await runServerTool(page, "ogg-a-mp3", ["voz.ogg"]);
  expect(body.subarray(0, 3).toString() === "ID3" || (body[0] === 0xff && (body[1] & 0xe0) === 0xe0)).toBe(true);
});

test("word-a-pdf con Gotenberg", async ({ page }) => {
  test.skip(!existsSync(path.join(FIXTURES, "carta.docx")), "Sin LibreOffice para generar el DOCX de prueba");
  const body = await runServerTool(page, "word-a-pdf", ["carta.docx"]);
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
});

test("pdf-a-word", async ({ page }) => {
  const body = await runServerTool(page, "pdf-a-word", ["texto.pdf"]);
  expect(body.subarray(0, 2).toString()).toBe("PK");
});

test("descarga con token manipulado: 403", async ({ page }) => {
  await page.goto("/es/comprimir-pdf");
  await page.locator('input[type="file"]').setInputFiles(path.join(FIXTURES, "texto.pdf"));
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 180_000 });
  const href = (await link.getAttribute("href"))!.replace("t=", "t=0");
  expect((await page.request.get(href)).status()).toBe(403);
});

test("pago con FakePaymentProvider", async ({ page }) => {
  const email = `e2e-${Date.now()}@ejemplo.test`;
  await page.goto("/es/registro");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill("contrasena-de-prueba");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Te hemos enviado un correo")).toBeVisible();
  // Mailpit: abre el enlace de confirmación.
  await page.goto(await verificationLink(page, email));
  await page.goto("/es/precios");
  await page.getByRole("button", { name: "Mensual", exact: true }).click();
  await page.waitForURL(/\/es\/cuenta\?pago=ok/);
  await expect(page.getByText("Pago completado")).toBeVisible();
  await expect(page.locator("strong", { hasText: "pro" })).toBeVisible();
});

// 16.1: chat-pdf con LLM falso en la pila completa (workerai sin clave y en desarrollo usa el proveedor falso).
test("chat-pdf con el LLM falso", async ({ page }) => {
  const email = `e2e-chat-${Date.now()}@ejemplo.test`;
  await page.goto("/es/registro");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill("contrasena-de-prueba");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Te hemos enviado un correo")).toBeVisible();
  await page.goto(await verificationLink(page, email));
  await page.goto("/es/chat-pdf");
  await page.locator("[data-chat-file]").setInputFiles(path.join(FIXTURES, "texto.pdf"));
  await page.locator("[data-ai-consent]").check();
  await page.getByRole("button", { name: "Preparar el documento", exact: true }).click();
  await expect(page.locator("[data-chat-ready]")).toBeVisible({ timeout: 120_000 });
  await page.locator("[data-chat-input]").fill("¿Qué dice la primera página?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.locator('[data-chat-message="assistant"]').last()).toContainText("Respuesta de prueba", { timeout: 60_000 });
});
