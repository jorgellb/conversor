import { readFileSync } from "node:fs";

import { PDFDocument } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";
import { prepareZXingModule, readBarcodes } from "zxing-wasm/reader";

// generar-codigo-qr y leer-codigo-qr (A.1, 7.11 y 16.6) en Chromium; la lectura de control se hace también aquí, en Node.
const zxingWasm = readFileSync(require.resolve("zxing-wasm/reader/zxing_reader.wasm"));
prepareZXingModule({
  overrides: {
    instantiateWasm(imports: WebAssembly.Imports, done: (instance: WebAssembly.Instance) => void) {
      void WebAssembly.instantiate(zxingWasm, imports).then(({ instance }) => done(instance));
      return {};
    },
  },
});

async function readQr(bytes: Buffer) {
  return readBarcodes(new Uint8Array(bytes), { formats: ["QRCode"], tryHarder: true });
}

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

async function generate(page: Page): Promise<Buffer> {
  await expect(page.locator("[data-qr-preview]")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Generar código QR" }).click();
  const link = page.getByRole("link", { name: /^Descargar codigo-qr\./ });
  await expect(link).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return readFileSync(await download.path());
}

test("generar-codigo-qr: URL en PNG, comprobada y leída de nuevo por leer-codigo-qr, sin subir nada", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const sent = watchUploads(page);
  await page.goto("/es/generar-codigo-qr");
  await page.getByLabel("Dirección").fill("ejemplo.test/qr");
  const png = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  await expect(page.getByText("Comprobado: el código se lee correctamente.")).toBeVisible();
  const [result] = await readQr(png);
  expect(result.text).toBe("https://ejemplo.test/qr");
  expect(result.ecLevel).toBe("Q");
  await page.getByRole("button", { name: "Copiar imagen" }).click();
  await expect(page.getByRole("button", { name: "Imagen copiada" })).toBeVisible();

  await page.goto("/es/leer-codigo-qr");
  await page.locator('input[type="file"]').setInputFiles({ name: "codigo-qr.png", mimeType: "image/png", buffer: png });
  await page.getByRole("button", { name: "Empezar", exact: true }).click();
  await expect(page.locator("code").first()).toHaveText("https://ejemplo.test/qr", { timeout: 30_000 });
  await expect(page.getByText("codigo-qr.png: 1 código (enlace).")).toBeVisible();
  expect(sent).toEqual([]);
});

test("generar-codigo-qr: con logotipo se fuerza la corrección H y zxing-cpp lo lee (16.6)", async ({ page }) => {
  await page.goto("/es/generar-codigo-qr");
  await page.getByLabel("Dirección").fill("https://ejemplo.test/logo");
  const logo = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 80;
    const g = c.getContext("2d")!;
    g.fillStyle = "#c00";
    g.fillRect(0, 0, 80, 80);
    g.fillStyle = "#fff";
    g.fillRect(25, 15, 30, 50);
    return c.toDataURL("image/png").split(",")[1];
  });
  await page.locator('input[type="file"][accept*=".png"]').setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: Buffer.from(logo, "base64") });
  await expect(page.getByRole("img", { name: "Logotipo elegido" })).toBeVisible();
  await page.getByLabel("Quitar los módulos de detrás del logotipo").check();
  const png = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  const [result] = await readQr(png);
  expect(result.text).toBe("https://ejemplo.test/logo");
  expect(result.ecLevel).toBe("H");
});

test("generar-codigo-qr: WiFi en SVG, transferencia SEPA en PDF vectorial y modo Kanji", async ({ page }) => {
  await page.goto("/es/generar-codigo-qr");
  await page.getByLabel("Tipo de contenido").selectOption("wifi");
  await page.getByLabel("Nombre de la red (SSID)").fill("Casa");
  await page.getByLabel("Contraseña").fill("clave;secreta");
  await page.getByLabel("Formato").selectOption("svg");
  const svg = await generate(page);
  expect(svg.toString("utf-8")).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"[^>]*width="500"/);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");

  await page.getByLabel("Tipo de contenido").selectOption("sepa");
  await page.getByLabel("Beneficiario").fill("Producto Demo");
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1333");
  await expect(page.locator("[data-qr-problem]")).toHaveText(/El IBAN no es válido/);
  await expect(page.getByRole("button", { name: "Generar código QR" })).toBeDisabled();
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1332");
  await page.getByLabel("Importe en euros (opcional)").fill("12.5");
  await page.getByLabel("Formato").selectOption("pdf");
  const pdf = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  const doc = await PDFDocument.load(pdf);
  expect(doc.getPageCount()).toBe(1);
  expect(Math.round(doc.getPage(0).getWidth())).toBe(375); // 500 px a 96 ppp

  await page.getByLabel("Tipo de contenido").selectOption("texto");
  await page.getByLabel("Texto", { exact: true }).fill("漢字テスト");
  await page.getByText("Estilo y opciones técnicas").click();
  await page.getByLabel("Modo").selectOption("kanji");
  await page.getByLabel("Formato").selectOption("png");
  const kanji = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  expect((await readQr(kanji))[0].text).toBe("漢字テスト");
  await page.getByLabel("Texto", { exact: true }).fill("€ ñ");
  await expect(page.locator("[data-qr-problem]")).toHaveText("El modo Kanji solo admite caracteres de doble byte de Shift_JIS («€» no lo es).");
  // En modo Byte el texto va en UTF-8 y se lee igual.
  await page.getByLabel("Modo").selectOption("byte");
  await page.getByLabel("Texto", { exact: true }).fill("€ ñ 漢字 😀");
  const utf8 = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  expect((await readQr(utf8))[0].text).toBe("€ ñ 漢字 😀");
});

test("generar-codigo-qr: estilo con degradado y borde, aviso si no se lee e importar y exportar la configuración", async ({ page }) => {
  await page.goto("/es/generar-codigo-qr");
  await page.getByLabel("Dirección").fill("https://ejemplo.test/estilo");
  await page.getByText("Estilo y opciones técnicas").click();
  await page.getByLabel("Degradado de los módulos", { exact: true }).selectOption("lineal");
  await page.getByLabel("Ángulo del degradado de los módulos").selectOption("45");
  await page.getByLabel("Forma de los módulos").selectOption("redondeado");
  await page.getByLabel("Borde", { exact: true }).check();
  const styled = await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "ok");
  expect((await readQr(styled))[0].text).toBe("https://ejemplo.test/estilo");

  const [exported] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Exportar configuración (JSON)" }).click()]);
  const config = JSON.parse(readFileSync(await exported.path(), "utf-8"));
  expect(config).toMatchObject({ herramienta: "generar-codigo-qr", opciones: { url: "https://ejemplo.test/estilo", modulos_degradado: "lineal", borde: true } });

  // Módulos blancos sobre fondo blanco: no se puede leer y se avisa.
  await page.locator('input[type="color"]').nth(1).evaluate((el: HTMLInputElement) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, "#ffffff");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.getByLabel("Degradado de los módulos", { exact: true }).selectOption("ninguno");
  await page.getByLabel("Dirección").fill("https://ejemplo.test/blanco");
  await generate(page);
  await expect(page.locator("[data-qr-check]")).toHaveAttribute("data-qr-check", "fail");
  await expect(page.getByText(/^No se ha podido leer el código generado/)).toBeVisible();

  await page.getByLabel("Importar configuración").setInputFiles({ name: "codigo-qr.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(config)) });
  await expect(page.getByLabel("Dirección")).toHaveValue("https://ejemplo.test/estilo");
  await expect(page.getByLabel("Degradado de los módulos", { exact: true })).toHaveValue("lineal");
});

test("leer-codigo-qr: un QR dentro de un PDF, en inglés", async ({ page }) => {
  await page.goto("/es/generar-codigo-qr");
  await page.getByLabel("Tipo de contenido").selectOption("texto");
  await page.getByLabel("Texto", { exact: true }).fill("Factura 2026-001");
  const png = await generate(page);
  const doc = await PDFDocument.create();
  doc.addPage([400, 400]);
  const pdfPage = doc.addPage([595, 842]);
  pdfPage.drawImage(await doc.embedPng(png), { x: 400, y: 650, width: 120, height: 120 });
  await page.goto("/en/qr-code-reader");
  await page.locator('input[type="file"]').setInputFiles({ name: "invoice.pdf", mimeType: "application/pdf", buffer: Buffer.from(await doc.save()) });
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.locator("code").first()).toHaveText("Factura 2026-001", { timeout: 30_000 });
  await expect(page.getByText("invoice.pdf: 1 code (text).")).toBeVisible();
  const link = page.getByRole("link", { name: /codigos-leidos\.csv/ });
  const [csv] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(readFileSync(await csv.path(), "utf-8")).toContain("invoice.pdf,2,QRCode,Factura 2026-001");
});
