import { readFileSync } from "node:fs";

import { PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, StandardFonts } from "@cantoo/pdf-lib";
import { expect, test, type Page } from "@playwright/test";

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

async function textPdf(pages: string[][], size: [number, number] = [400, 500]): Promise<Buffer> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (const lines of pages) {
    const p = doc.addPage(size);
    lines.forEach((t, i) => p.drawText(t, { x: 40, y: size[1] - 60 - i * 24, size: 16, font }));
  }
  return Buffer.from(await doc.save());
}

async function download(page: Page, link: ReturnType<Page["locator"]>): Promise<Buffer> {
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return readFileSync(await d.path());
}

test("cortar-paginas-por-la-mitad e imprimir-pdf con asistente de doble cara", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/cortar-paginas-por-la-mitad");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "escaneo.pdf", mimeType: "application/pdf", buffer: await textPdf([["A"], ["B"]], [800, 500]) });
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  expect((await PDFDocument.load(await download(page, link))).getPageCount()).toBe(4);

  await page.goto("/es/imprimir-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "cinco.pdf", mimeType: "application/pdf", buffer: await textPdf([["1"], ["2"], ["3"], ["4"], ["5"]]) });
  await page.getByLabel("Doble cara").selectOption("manual");
  await page.getByRole("button", { name: "Empezar" }).click();
  const assistant = page.getByRole("list", { name: "Asistente de doble cara" });
  await expect(assistant).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[data-sheet]")).toHaveCount(3, { timeout: 30_000 });
  await assistant.getByRole("button", { name: "Imprimir anversos" }).click();
  await expect(page.locator("iframe[data-print]")).toHaveCount(1);
  await expect(assistant.getByRole("button", { name: "Imprimir reversos" })).toBeEnabled();
  expect(sent).toEqual([]);
});

test("montar-pdf: mover páginas entre documentos y guardar cada uno", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/montar-pdf");
  await page.locator('input[type="file"]').first().setInputFiles([
    { name: "uno.pdf", mimeType: "application/pdf", buffer: await textPdf([["U1"], ["U2"], ["U3"]]) },
    { name: "dos.pdf", mimeType: "application/pdf", buffer: await textPdf([["D1"]]) },
  ]);
  const uno = page.locator('[data-column="uno"]');
  const dos = page.locator('[data-column="dos"]');
  await expect(uno.locator("[data-card]")).toHaveCount(3, { timeout: 30_000 });
  await expect(dos.locator("[data-card]")).toHaveCount(1);
  await uno.locator('[data-card="uno.pdf#3"]').getByLabel("Mover a…").selectOption({ label: "dos" });
  await expect(dos.locator("[data-card]")).toHaveCount(2);
  await dos.locator('[data-card="dos.pdf#1"]').getByRole("button", { name: "Girar 90°" }).click();
  await page.getByRole("button", { name: "Guardar los documentos" }).click();
  const links = page.getByRole("region", { name: "Resultado" }).locator("a[download]");
  await expect(links).toHaveCount(3, { timeout: 30_000 });
  const second = await PDFDocument.load(await download(page, links.nth(1)));
  expect(second.getPageCount()).toBe(2);
  expect(second.getPage(0).getRotation().angle).toBe(90);
  expect(sent).toEqual([]);
});

test("marcadores-pdf: crear un árbol y guardarlo", async ({ page }) => {
  await page.goto("/es/marcadores-pdf");
  await page.locator('input[type="file"]').setInputFiles({ name: "libro.pdf", mimeType: "application/pdf", buffer: await textPdf([["Uno"], ["Dos"], ["Tres"]]) });
  await expect(page.getByText("Este PDF no tiene marcadores.")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Añadir", exact: true }).click();
  await page.getByLabel("Título").fill("Capítulo 1");
  await page.getByRole("button", { name: "Añadir dentro" }).click();
  await page.getByLabel("Título").fill("Sección 1.1");
  await page.getByLabel("Página de destino").fill("3");
  await page.getByRole("button", { name: "Guardar el PDF" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const doc = await PDFDocument.load(await download(page, link));
  const outlines = doc.catalog.lookup(PDFName.of("Outlines"), PDFDict);
  const first = outlines.lookup(PDFName.of("First"), PDFDict);
  expect((first.lookup(PDFName.of("Title")) as PDFHexString).decodeText()).toBe("Capítulo 1");
  const child = first.lookup(PDFName.of("First"), PDFDict);
  expect((child.lookup(PDFName.of("Title")) as PDFHexString).decodeText()).toBe("Sección 1.1");
  const dest = child.lookup(PDFName.of("Dest"), PDFArray);
  expect(dest.get(0).toString()).toBe(doc.getPage(2).ref.toString());
});

test("comparar-pdf: lista de cambios, superposición, deslizador e informe", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/comparar-pdf");
  await page.getByLabel("Archivo A (original)").setInputFiles({ name: "a.pdf", mimeType: "application/pdf", buffer: await textPdf([["El precio es 100 euros", "Entrega en Madrid"]]) });
  await page.getByLabel("Archivo B (nuevo)").setInputFiles({ name: "b.pdf", mimeType: "application/pdf", buffer: await textPdf([["El precio es 120 euros", "Entrega en Madrid"]]) });
  const changes = page.getByRole("complementary", { name: "Cambios" });
  await expect(changes).toContainText("1 cambio", { timeout: 30_000 });
  await expect(changes).toContainText("Cambiado");
  await expect(page.locator('[data-cmp-page="a1"] [data-change="changed"]')).toHaveCount(1);
  await page.getByRole("tab", { name: "Superposición" }).click();
  await expect(page.locator('canvas[data-overlay][data-rendered="1"]')).toHaveCount(1, { timeout: 30_000 });
  await page.getByRole("tab", { name: "Deslizador" }).click();
  await expect(page.locator("[data-slider-b]")).toHaveCount(1);
  await page.getByRole("button", { name: "Informe PDF" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  expect((await download(page, link)).subarray(0, 5).toString()).toBe("%PDF-");
  expect(sent).toEqual([]);
});

test("buscar-en-pdf: varios archivos, página resaltada y CSV", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/buscar-en-pdf");
  await page.locator('input[type="file"]').setInputFiles([
    { name: "contrato.pdf", mimeType: "application/pdf", buffer: await textPdf([["Contrato de alquiler"], ["Cláusula del contrato"]]) },
    { name: "factura.pdf", mimeType: "application/pdf", buffer: await textPdf([["Factura sin nada"]]) },
  ]);
  await page.getByLabel("Texto a buscar").fill("contrato");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  const results = page.getByRole("region", { name: "Resultados" });
  await expect(results).toContainText("2 resultados", { timeout: 30_000 });
  await results.locator("[data-result]").nth(1).click();
  await expect(page.getByRole("dialog").locator("[data-hit]")).toHaveCount(1, { timeout: 30_000 });
  const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Exportar a CSV" }).click()]);
  const text = readFileSync(await csv.path(), "utf8");
  expect(text).toContain('"contrato.pdf";"2"');
  expect(sent).toEqual([]);
});

test("copiar-de-pdf: selección libre sin subir nada y bloques reconocidos en el servidor que se copian con un clic", async ({ page, context }) => {
  // El servidor se simula: subida tus, creación del trabajo y descarga de bloques.json (la parte de Docling tiene sus
  // propias pruebas en tests/test_desde_pdf_docling.py).
  const WEB = "http://127.0.0.1:3100", API = "http://127.0.0.1:8100", UP = "http://127.0.0.1:8180", FILES = "http://127.0.0.1:8190";
  const cors = {
    "Access-Control-Allow-Origin": WEB, "Access-Control-Allow-Methods": "GET, POST, PATCH, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Tus-Resumable, Upload-Length, Upload-Offset, Upload-Metadata, Upload-Defer-Length, X-Requested-With",
    "Access-Control-Expose-Headers": "Location, Upload-Offset, Upload-Length, Tus-Resumable",
  };
  const blocks = {
    version: 1, source: "informe.pdf", pages: [{ number: 1, width: 400, height: 500 }],
    blocks: [
      { id: "b1", page: 1, type: "titulo", bbox: [38, 44, 220, 66], text: "Informe de ventas", html: "<h2>Informe de ventas</h2>", markdown: "## Informe de ventas" },
      { id: "b2", page: 1, type: "tabla", bbox: [38, 92, 360, 140], text: "Producto\tUnidades\nManzanas\t12",
        html: "<table><thead><tr><th>Producto</th><th>Unidades</th></tr></thead><tbody><tr><td>Manzanas</td><td>12</td></tr></tbody></table>",
        markdown: "| Producto | Unidades |\n|---|---|\n| Manzanas | 12 |", header: ["Producto", "Unidades"], rows: [["Manzanas", "12"]] },
    ],
  };
  let offset = 0;
  let created: { tool?: string; upload_ids?: string[] } = {};
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: WEB });
  await page.addInitScript(() => window.localStorage.setItem("conversor:anon", JSON.stringify({ token: "anon-e2e", until: Date.now() + 86_400_000 })));
  await page.route(`${UP}/**`, (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.method() === "POST") return route.fulfill({ status: 201, headers: { ...cors, Location: `${UP}/files/subida1`, "Tus-Resumable": "1.0.0" } });
    if (req.method() === "PATCH") {
      offset += req.postDataBuffer()?.length ?? 0;
      return route.fulfill({ status: 204, headers: { ...cors, "Upload-Offset": String(offset), "Tus-Resumable": "1.0.0" } });
    }
    return route.fulfill({ status: 200, headers: { ...cors, "Upload-Offset": String(offset), "Upload-Length": String(offset), "Tus-Resumable": "1.0.0" } });
  });
  await page.route(`${API}/**`, (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) {
      created = req.postDataJSON();
      const outputs = [
        { name: "bloques.json", size: 1, mime: "application/json", note: null, url: `${FILES}/d/t1/bloques.json?t=x`, url_expires_in: 900 },
        { name: "informe.md", size: 1, mime: "text/markdown", note: null, url: `${FILES}/d/t1/informe.md?t=x`, url_expires_in: 900 },
      ];
      return route.fulfill({ status: 201, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify({
        id: "t1", tool: "copiar-de-pdf", status: "succeeded", progress: 1, message: null, error: null, expires_at: null,
        inputs: [{ name: "informe.pdf", size: offset }], outputs }) });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.route(`${FILES}/**`, (route) => route.fulfill({
    status: 200, headers: { ...cors, "Content-Type": route.request().url().includes(".json") ? "application/json" : "text/markdown" },
    body: route.request().url().includes(".json") ? JSON.stringify(blocks) : "## Informe de ventas\n",
  }));

  const sent = watchUploads(page);
  await page.goto("/es/copiar-de-pdf");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "informe.pdf", mimeType: "application/pdf", buffer: await textPdf([["Informe de ventas", "Producto Unidades"]]) });
  const pageBox = page.getByRole("group", { name: "Página 1" });
  await expect(pageBox.locator("canvas")).toHaveAttribute("data-rendered", "1");
  await expect(pageBox.locator(".text-layer span").first()).toBeVisible();
  expect(sent).toEqual([]);  // ver y seleccionar no sube nada

  await page.getByRole("button", { name: "Reconocer los bloques" }).click();
  const table = page.getByRole("button", { name: "Tabla: Producto · Unidades" });
  await expect(table).toBeVisible();
  expect(created).toEqual({ tool: "copiar-de-pdf", upload_ids: ["subida1"], options: {} });
  await table.hover();
  await table.click();
  await expect(page.locator("[data-toast]")).toHaveText("Copiado: Tabla de la página 1.");
  const clip = await page.evaluate(async () => {
    const out: Record<string, string> = {};
    for (const item of await navigator.clipboard.read()) for (const type of item.types) out[type] = await (await item.getType(type)).text();
    return out;
  });
  expect(clip["text/plain"]).toBe("Producto\tUnidades\r\nManzanas\t12");
  expect(clip["text/html"]).toContain("<th>Producto</th>");

  await page.getByLabel("Copiar como").selectOption("markdown");
  await page.getByRole("button", { name: "Título: Informe de ventas" }).click();
  // La escritura en el portapapeles es asíncrona: se espera a que llegue (con carga, la lectura podía adelantarse).
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe("## Informe de ventas");
  await page.getByRole("radio", { name: "Selección libre" }).click();
  await expect(page.getByRole("button", { name: "Título: Informe de ventas" })).toHaveCount(0);
});
