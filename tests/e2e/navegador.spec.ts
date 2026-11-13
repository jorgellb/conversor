import { readFileSync } from "node:fs";

import { PDFDocument, StandardFonts } from "@cantoo/pdf-lib";
import { expect, test, type Page, type Request } from "@playwright/test";

async function pdf(pages: number, text: string): Promise<Buffer> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < pages; i += 1) doc.addPage([400, 500]).drawText(`${text} ${i + 1}`, { x: 40, y: 250, size: 18, font });
  return Buffer.from(await doc.save());
}

/** Registra las peticiones con cuerpo: una herramienta de navegador no debe enviar ninguna. */
function watchUploads(page: Page): Request[] {
  const sent: Request[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r);
  });
  return sent;
}

async function runAndDownload(page: Page) {
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 60_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return download;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`));
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().startsWith("CSP")) throw new Error(m.text());
  });
});

test("unir-pdf en el navegador no envía el archivo", async ({ page }) => {
  await page.goto("/es/unir-pdf");
  await page.locator('input[type="file"]').setInputFiles([
    { name: "uno.pdf", mimeType: "application/pdf", buffer: await pdf(3, "Uno") },
    { name: "dos.pdf", mimeType: "application/pdf", buffer: await pdf(2, "Dos") },
  ]);
  const sent = watchUploads(page);
  const download = await runAndDownload(page);
  const merged = await PDFDocument.load(readFileSync(await download.path()));
  expect(merged.getPageCount()).toBe(5);
  expect(sent.map((r) => r.url())).toEqual([]);
});

test("pdf-a-jpg con PDFium en WebAssembly", async ({ page }) => {
  await page.goto("/es/pdf-a-jpg");
  await page.locator('input[type="file"]').setInputFiles([{ name: "doc.pdf", mimeType: "application/pdf", buffer: await pdf(2, "Hoja") }]);
  const sent = watchUploads(page);
  const download = await runAndDownload(page);
  expect(download.suggestedFilename()).toBe("doc-imagenes.zip");
  expect(sent).toEqual([]);
});

test("numerar-paginas-pdf con Noto Sans y tildes", async ({ page }) => {
  await page.goto("/es/numerar-paginas-pdf");
  await page.locator('input[type="file"]').setInputFiles([{ name: "n.pdf", mimeType: "application/pdf", buffer: await pdf(3, "Texto") }]);
  await page.getByLabel("Patrón").fill("Página {NUM} de {CNT}");
  const download = await runAndDownload(page);
  const doc = await PDFDocument.load(readFileSync(await download.path()));
  expect(doc.getPageCount()).toBe(3);
});

test("generar-contrasena y página en inglés con hreflang", async ({ page }) => {
  await page.goto("/es/generar-contrasena");
  await page.getByRole("button", { name: "Generar" }).click();
  await expect(page.locator("code").first()).toHaveText(/^.{16}$/);
  await page.goto("/en/compress-pdf");
  await expect(page.locator("h1")).toHaveText("Compress PDF");
  await expect(page.locator('link[rel="alternate"][hreflang="es"]')).toHaveAttribute("href", /\/es\/comprimir-pdf$/);
});

test("cabeceras de seguridad de la web", async ({ request }) => {
  const res = await request.get("/es/comprimir-pdf");
  const csp = res.headers()["content-security-policy"];
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'wasm-unsafe-eval'/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(res.headers()["strict-transport-security"]).toContain("includeSubDomains");
  expect(res.headers()["permissions-policy"]).toContain("camera=()");
});

test("crear-pdf enlaza las herramientas existentes y web-a-pdf pide la URL antes de empezar", async ({ page }) => {
  await page.goto("/es/crear-pdf");
  await expect(page.getByRole("heading", { level: 1, name: "Crear un PDF" })).toBeVisible();
  await expect(page).toHaveTitle(/Crear un PDF/);
  await page.getByRole("link", { name: /Web a PDF/ }).click();
  await expect(page).toHaveURL(/\/es\/web-a-pdf$/);
  const start = page.getByRole("button", { name: "Empezar" });
  await expect(start).toBeDisabled();
  await page.getByLabel("Dirección de la página o del documento").fill("https://www.ejemplo.com/");
  await expect(start).toBeEnabled();
  const en = await page.request.get("/en/create-pdf");
  expect(en.status()).toBe(200);
});

test("seguir con otra herramienta pasa el resultado del navegador a la siguiente", async ({ page }) => {
  const doc = await PDFDocument.create();
  for (let i = 0; i < 2; i += 1) doc.addPage([300, 300]);
  await page.goto("/es/girar-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "dos.pdf", mimeType: "application/pdf", buffer: Buffer.from(await doc.save()) });
  await page.getByRole("button", { name: "Empezar" }).click();
  await expect(page.locator("a[download]").first()).toBeVisible({ timeout: 30_000 });
  await page.getByText("Seguir con otra herramienta").click();
  await page.getByRole("button", { name: "Numerar páginas de un PDF" }).click();
  await expect(page).toHaveURL(/\/es\/numerar-paginas-pdf$/);
  await expect(page.getByText("dos-girado.pdf").or(page.getByText(/dos.*\.pdf/)).first()).toBeVisible({ timeout: 15_000 });
});

test("Google Drive y Dropbox apagados por defecto: ni botones ni dominios en la CSP", async ({ page }) => {
  const res = await page.goto("/es/unir-pdf");
  expect(res!.headers()["content-security-policy"]).not.toMatch(/google|dropbox/);
  await expect(page.getByRole("button", { name: /Google Drive|Dropbox/ })).toHaveCount(0);
  const config = await (await page.request.get("/api/config")).json();
  expect(config.gdrive).toBeNull();
  expect(config.dropbox).toBeNull();
});

test("metadatos-pdf rellena el formulario y eliminar-metadatos-pdf enseña lo que borrará, sin subir nada", async ({ page }) => {
  const doc = await PDFDocument.create();
  doc.addPage([200, 200]);
  doc.setTitle("Informe anual");
  doc.setAuthor("Ana García");
  const bytes = Buffer.from(await doc.save());
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  await page.goto("/es/metadatos-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "informe.pdf", mimeType: "application/pdf", buffer: bytes });
  await expect(page.getByLabel("Título")).toHaveValue("Informe anual", { timeout: 15_000 });
  await expect(page.getByLabel("Autor")).toHaveValue("Ana García");
  await page.goto("/es/eliminar-metadatos-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "informe.pdf", mimeType: "application/pdf", buffer: bytes });
  const panel = page.getByRole("status", { name: "Se va a borrar:" });
  await expect(panel).toContainText("Informe anual", { timeout: 15_000 });
  await expect(panel).toContainText("Ana García");
  expect(sent).toEqual([]);
});

test("lote C: el alias pub-a-pdf apunta a publisher-a-pdf y HEIC apagado explica cómo pasar a JPEG", async ({ page }) => {
  await page.goto("/es/pub-a-pdf");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/es\/publisher-a-pdf$/);
  await expect(page.locator('link[rel="alternate"][hreflang="en"]')).toHaveAttribute("href", /\/en\/publisher-to-pdf$/);
  await page.goto("/es/heic-a-pdf");
  await expect(page.getByRole("heading", { name: "Cómo pasar fotos HEIC a JPEG" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Cómo pasar fotos HEIC a JPEG" }).getByRole("link", { name: "JPG a PDF" })).toHaveAttribute("href", "/es/jpg-a-pdf");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await page.goto("/en/heic-to-pdf");
  await expect(page.getByRole("heading", { name: "How to turn HEIC photos into JPEG" })).toBeVisible();
});

test("lote C: solicitud-de-empleo-pdf marca carta, CV y adjuntos", async ({ page }) => {
  await page.goto("/es/solicitud-de-empleo-pdf");
  const files = ["carta.pdf", "cv.pdf", "titulo.pdf"].map((name) => ({ name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") }));
  await page.locator('input[type="file"]').setInputFiles(files);
  const items = page.getByRole("region", { name: "Archivos elegidos" }).getByRole("listitem");
  await expect(items.nth(0)).toContainText("Carta de presentación");
  await expect(items.nth(1)).toContainText("Currículum");
  await expect(items.nth(2)).toContainText("Adjunto");
});

test("lote D: pdf-a-webp en el navegador sin subir nada; CMYK se ofrece solo como opción de servidor", async ({ page }) => {
  await page.goto("/es/pdf-a-webp");
  await page.locator('input[type="file"]').setInputFiles([{ name: "uno.pdf", mimeType: "application/pdf", buffer: await pdf(1, "Hoja") }]);
  const sent = watchUploads(page);
  const download = await runAndDownload(page);
  expect(download.suggestedFilename()).toBe("uno-1.webp");
  const bytes = readFileSync(await download.path());
  expect(bytes.subarray(0, 4).toString("latin1")).toBe("RIFF");
  expect(bytes.subarray(8, 12).toString("latin1")).toBe("WEBP");
  expect(sent).toEqual([]);
  await page.goto("/es/pdf-a-jpg");
  await expect(page.getByRole("option", { name: "CMYK con perfil ICC (JPG, en el servidor)" })).toHaveCount(1);
});

test("lote D: convertir-desde-pdf cambia el formulario según el formato", async ({ page }) => {
  await page.goto("/es/convertir-desde-pdf");
  const options = page.getByRole("region", { name: "Opciones" });
  const field = (name: string) => options.getByLabel(name, { exact: true });
  await expect(field("Formato de salida")).toHaveValue("docx");
  await expect(field("Modo")).toBeVisible();
  await expect(field("Separador")).toHaveCount(0);
  await field("Formato de salida").selectOption("csv");
  await expect(field("Separador")).toBeVisible();
  await expect(field("Modo")).toHaveCount(0);
  await field("Formato de salida").selectOption("jpg");
  await expect(field("Calidad (%)")).toBeVisible();
  await field("Formato de salida").selectOption("png");
  await expect(field("Calidad (%)")).toHaveCount(0);
  await field("Formato de salida").selectOption("pdfa");
  await expect(field("Nivel")).toBeVisible();
  await expect(field("Páginas")).toHaveCount(0);
});
