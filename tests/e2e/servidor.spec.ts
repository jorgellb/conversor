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

/** Cuenta nueva con el correo confirmado (Mailpit). */
async function signUp(page: Page, prefix: string): Promise<string> {
  const email = `${prefix}-${Date.now()}@ejemplo.test`;
  await page.goto("/es/registro");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill("contrasena-de-prueba");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Te hemos enviado un correo")).toBeVisible();
  await page.goto(await verificationLink(page, email));
  return email;
}

/** Pase de 24 h con el pago de prueba de la pila de desarrollo (PAYMENT_PROVIDER=fake, D-273). */
async function buyPass(page: Page) {
  await page.goto("/es/pase");
  await page.locator("[data-pass-waiver]").check();
  await page.locator("[data-pass-fake]").click();
  await expect(page.locator("[data-pass-paid]")).toContainText("Tu pase está activo hasta", { timeout: 30_000 });
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

test("factura-electronica-a-pdf: PDF/A-3b de Gotenberg con el XML incrustado y veraPDF (F4-D2)", async ({ page }) => {
  const body = await runServerTool(page, "factura-electronica-a-pdf", ["facturas/ubl-peppol.xml"]);
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  await expect(page.getByText(/PDF\/A-3 con el XML original incrustado sin cambios \(ubl-peppol\.xml\)\. Cumple: PDF\/A-3b\./)).toBeVisible();
});

test("pdf-a-word: sin pase ofrece el pase; con el pase, convierte (D-273)", async ({ page }) => {
  await page.goto("/es/pdf-a-word");
  await page.locator('input[type="file"]').setInputFiles(path.join(FIXTURES, "texto.pdf"));
  await page.getByRole("button", { name: "Empezar" }).click();
  await expect(page.locator("[data-pass-offer]")).toBeVisible();
  await signUp(page, "e2e-word");
  await buyPass(page);
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

test("pase de 24 h: pago de prueba, factura en PDF y pedido en la cuenta (D-273)", async ({ page }) => {
  await signUp(page, "e2e-pase");
  await buyPass(page);
  await page.getByRole("link", { name: "Ver la factura" }).click();
  await page.waitForURL(/\/es\/cuenta/);
  await expect(page.locator('[data-pass-state="active"]')).toBeVisible();
  await expect(page.getByRole("cell", { name: /^S\d{4}-\d{6}$/ })).toBeVisible();
  await expect(page.getByText("Pagado")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Descargar PDF" }).click();
  const file = await (await download).path();
  expect(readFileSync(file!).subarray(0, 5).toString()).toBe("%PDF-");
});

// 16.1: chat-pdf con LLM falso en la pila completa (workerai sin clave y en desarrollo usa el proveedor falso).
test("chat-pdf con el LLM falso (con el pase, D-273)", async ({ page }) => {
  await signUp(page, "e2e-chat");
  await buyPass(page);
  await page.goto("/es/chat-pdf");
  await page.locator("[data-chat-file]").setInputFiles(path.join(FIXTURES, "texto.pdf"));
  await page.locator("[data-ai-consent]").check();
  await page.getByRole("button", { name: "Preparar el documento", exact: true }).click();
  await expect(page.locator("[data-chat-ready]")).toBeVisible({ timeout: 120_000 });
  await page.locator("[data-chat-input]").fill("¿Qué dice la primera página?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.locator('[data-chat-message="assistant"]').last()).toContainText("Respuesta de prueba", { timeout: 60_000 });
});

/** Último correo que recibe `email` en Mailpit con `subject` en el asunto (texto plano). */
async function mailText(page: Page, email: string, subject: string): Promise<string> {
  let id = "";
  await expect.poll(async () => {
    const found = await (await page.request.get(`http://localhost:8025/api/v1/search?query=${encodeURIComponent(`to:${email} subject:"${subject}"`)}`)).json();
    id = found.messages?.[0]?.ID ?? "";
    return id;
  }, { timeout: 60_000 }).not.toBe("");
  return (await (await page.request.get(`http://localhost:8025/api/v1/message/${id}`)).json()).Text as string;
}

// 7.7 y cierre de F4 (17): solicitar-firmas de extremo a extremo con Mailpit, el sello de desarrollo de SoftHSM2 y la
// TSA de certomancer: invitación, código, firma, sello final B-LT, certificado de auditoría y descarga.
test("solicitar-firmas: invitación, código por correo, firma y documento sellado", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const owner = `e2e-pide-${Date.now()}@ejemplo.test`;
  const signer = `e2e-firma-${Date.now()}@ejemplo.test`;
  await page.goto("/es/registro");
  await page.getByLabel("Correo electrónico").fill(owner);
  await page.getByLabel("Contraseña").fill("contrasena-de-prueba");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Te hemos enviado un correo")).toBeVisible();
  await page.goto(await verificationLink(page, owner));
  await page.goto("/es/solicitar-firmas");
  await page.getByLabel("Documento PDF").setInputFiles(path.join(FIXTURES, "texto.pdf"));
  const row = page.locator("[data-signer='0']");
  await row.getByLabel("Nombre").fill("Eva Firmante");
  await row.getByLabel("Correo").fill(signer);
  await page.getByRole("button", { name: "Preparar y enviar las invitaciones" }).click();
  await expect(page.getByRole("status")).toContainText("Solicitud de «texto.pdf» creada", { timeout: 120_000 });

  const invite = await mailText(page, signer, "te pide que firmes");
  const link = /https?:\/\/\S+#[A-Za-z0-9_-]+/.exec(invite)![0];
  const other = await browser.newContext();
  const sp = await other.newPage();
  await sp.goto(link);
  await expect(sp.getByText(`${owner} te pide que firmes este documento, Eva Firmante.`)).toBeVisible();
  await sp.getByRole("button", { name: "Enviar el código" }).click();
  const code = /\b(\d{6})\b/.exec(await mailText(page, signer, "Tu código para firmar"))![1];
  await sp.getByLabel("Código").fill(code);
  await sp.getByRole("button", { name: "Dibujar o escribir la firma" }).click();
  const dialog = sp.getByRole("dialog", { name: "Firma" });
  await dialog.getByRole("tab", { name: "Escribir" }).click();
  await dialog.getByLabel("Tu nombre").fill("Eva Firmante");
  await dialog.getByRole("button", { name: "Usar la firma" }).click();
  await sp.getByRole("checkbox", { name: /Acepto firmar electrónicamente/ }).check();
  await sp.getByRole("button", { name: "Firmar", exact: true }).click();
  await expect(sp.getByText("Todos han firmado.")).toBeVisible({ timeout: 180_000 });
  const files = sp.locator("a[download]");
  await expect(files).toHaveCount(2);
  const signed = await sp.request.get((await files.nth(0).getAttribute("href"))!);
  expect(signed.status()).toBe(200);
  // Los diccionarios de firma nunca van comprimidos (su /Contents se rellena en el sitio): el del firmante y el final.
  const body = (await signed.body()).toString("latin1");
  expect(body.match(/\/ByteRange/g)?.length).toBe(2);
  const certificate = await sp.request.get((await files.nth(1).getAttribute("href"))!);
  expect(certificate.status()).toBe(200);
  expect((await mailText(page, owner, "ya está firmado por todos"))).toContain("/r/");
  await other.close();
});
