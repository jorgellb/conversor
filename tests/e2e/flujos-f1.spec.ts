import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFDocument, StandardFonts } from "@cantoo/pdf-lib";
import { zipSync, strToU8 } from "fflate";
import { expect, test, type Page, type Route } from "@playwright/test";

// 16.1 en el proyecto navegador: los flujos de servidor de comprimir, word-a-pdf, pdf-a-word y ogg-a-mp3, y el
// pago con FakePaymentProvider, con el servidor simulado (subida tus, trabajo con eventos, descarga firmada y
// /v1/billing). Comprueban lo que hace la web: qué sube, con qué metadatos, qué opciones manda (las del registro, que son
// las del Anexo A), cómo sigue el trabajo y qué enlace ofrece. El extremo a extremo con la pila real está en
// servidor.spec.ts (job e2e-compose de la CI), que usa los mismos textos y botones que estas pruebas. unir-pdf es de
// navegador y su prueba (el archivo no sale del dispositivo) está en navegador.spec.ts.
const WEB = "http://127.0.0.1:3100", API = "http://127.0.0.1:8100", UP = "http://127.0.0.1:8180", FILES = "http://127.0.0.1:8190";
const cors = {
  "Access-Control-Allow-Origin": WEB, "Access-Control-Allow-Methods": "GET, POST, PATCH, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept-Language, Tus-Resumable, Upload-Length, Upload-Offset, Upload-Metadata, Upload-Defer-Length, X-Requested-With",
  "Access-Control-Expose-Headers": "Location, Upload-Offset, Upload-Length, Tus-Resumable",
};

type Schema = { properties?: Record<string, { default?: unknown }> };
const REGISTRY = JSON.parse(readFileSync(path.join(__dirname, "..", "..", "packages", "registry", "registry.json"), "utf-8")) as
  { tools: { slug_es: string; options_schema: Schema }[] };

/** Opciones que manda la página sin tocar el formulario: las de options_schema con su valor por defecto. */
function defaults(slug: string): Record<string, unknown> {
  const tool = REGISTRY.tools.find((t) => t.slug_es === slug)!;
  return Object.fromEntries(Object.entries(tool.options_schema.properties ?? {}).map(([k, p]) => [k, p.default ?? null]));
}

async function pdf(pages: number): Promise<Buffer> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < pages; i += 1) doc.addPage([400, 500]).drawText(`Hoja ${i + 1}`, { x: 40, y: 250, size: 18, font });
  return Buffer.from(await doc.save());
}

/** DOCX mínimo válido (las partes que exige Word y que reconoce filetype por los bytes). */
function docx(): Buffer {
  const types = `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`;
  const rels = `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`;
  const body = `<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Carta de prueba</w:t></w:r></w:p></w:body></w:document>`;
  return Buffer.from(zipSync({ "[Content_Types].xml": strToU8(types), "_rels/.rels": strToU8(rels), "word/document.xml": strToU8(body) }));
}

/** Página Ogg con la cabecera de identificación de Vorbis (lo que mira filetype). */
function ogg(): Buffer {
  const head = Buffer.alloc(58);
  head.write("OggS", 0, "latin1");
  head[5] = 0x02;
  head[26] = 1;
  head[27] = 30;
  head.write("\x01vorbis", 28, "latin1");
  return head;
}

interface Server {
  metadata: Record<string, string>[];
  jobs: { tool: string; upload_ids: string[]; options: Record<string, unknown> }[];
  uploadedBytes: number;
}

/** Simula tus, la API de trabajos (queued → running por eventos → succeeded) y las descargas firmadas. */
async function mockServer(page: Page, output: { name: string; mime: string; body: Buffer }): Promise<Server> {
  const server: Server = { metadata: [], jobs: [], uploadedBytes: 0 };
  await page.addInitScript(() => window.localStorage.setItem("conversor:anon", JSON.stringify({ token: "anon-e2e", until: Date.now() + 86_400_000 })));
  await page.route(`${UP}/**`, (route: Route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.method() === "POST") {
      expect(req.headers()["authorization"]).toBe("Bearer anon-e2e");
      server.metadata.push(Object.fromEntries((req.headers()["upload-metadata"] ?? "").split(",").map((pair) => {
        const [k, v] = pair.trim().split(" ");
        return [k, Buffer.from(v ?? "", "base64").toString("utf-8")];
      })));
      return route.fulfill({ status: 201, headers: { ...cors, Location: `${UP}/files/subida${server.metadata.length}`, "Tus-Resumable": "1.0.0" } });
    }
    if (req.method() === "PATCH") {
      server.uploadedBytes += req.postDataBuffer()?.length ?? 0;
      return route.fulfill({ status: 204, headers: { ...cors, "Upload-Offset": String(server.uploadedBytes), "Tus-Resumable": "1.0.0" } });
    }
    return route.fulfill({ status: 200, headers: { ...cors, "Upload-Offset": String(server.uploadedBytes), "Upload-Length": String(server.uploadedBytes), "Tus-Resumable": "1.0.0" } });
  });
  const view = (status: string, progress: number) => {
    const tool = server.jobs[0]?.tool ?? "";
    return {
      id: "j1", tool, status, progress, message: null, error: null, expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      inputs: [{ name: "entrada", size: server.uploadedBytes }],
      outputs: status === "succeeded"
        ? [{ name: output.name, size: output.body.length, mime: output.mime, note: null, url: `${FILES}/d/00000000-0000-4000-8000-000000000001/${output.name}?t=firma`, url_expires_in: 900 }]
        : [],
    };
  };
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.method() === "POST" && url.pathname === "/v1/jobs") {
      server.jobs.push(req.postDataJSON());
      return route.fulfill({ status: 201, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(view("queued", 0)) });
    }
    if (url.pathname === "/v1/jobs/j1/events") {
      const events = [view("queued", 0), view("running", 0.5), view("succeeded", 1)].map((v) => `event: job\ndata: ${JSON.stringify(v)}\n\n`).join("");
      return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "text/event-stream" }, body: events });
    }
    if (url.pathname === "/v1/jobs/j1") return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(view("succeeded", 1)) });
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.route(`${FILES}/**`, (route: Route) => route.fulfill({
    status: 200, body: output.body,
    headers: { ...cors, "Content-Type": output.mime, "Content-Disposition": `attachment; filename="${output.name}"`, "Content-Security-Policy": "default-src 'none'; sandbox" },
  }));
  return server;
}

/** El mismo recorrido que runServerTool de servidor.spec.ts: elegir, «Empezar», enlace de descarga firmado. */
async function runServerTool(page: Page, slug: string, files: { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.goto(`/es/${slug}`);
  await page.locator('input[type="file"]').setInputFiles(files);
  await page.getByRole("button", { name: "Empezar" }).click();
  const link = page.locator("a[download]").first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const href = await link.getAttribute("href");
  expect(href).toMatch(/\/d\/[0-9a-f-]{36}\/.+\?t=/);
  // Uppy manda el último aviso de progreso con retraso; no puede devolver la página a «Subiendo…» (D-147).
  await page.waitForTimeout(1500);
  await expect(link).toBeVisible();
  await expect(page.getByText(/Subiendo/)).toHaveCount(0);
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  return { link, download: readFileSync(await download.path()) };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`));
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().startsWith("CSP")) throw new Error(m.text());
  });
});

const SERVER_TOOLS = [
  { slug: "comprimir-pdf", input: async () => ({ name: "fotos.pdf", mimeType: "application/pdf", buffer: await pdf(3) }),
    output: { name: "fotos-comprimido.pdf", mime: "application/pdf" } },
  { slug: "word-a-pdf", input: async () => ({ name: "carta.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: docx() }),
    output: { name: "carta.pdf", mime: "application/pdf" } },
  { slug: "pdf-a-word", input: async () => ({ name: "texto.pdf", mimeType: "application/pdf", buffer: await pdf(2) }),
    output: { name: "texto.docx", mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" } },
  { slug: "ogg-a-mp3", input: async () => ({ name: "voz.ogg", mimeType: "audio/ogg", buffer: ogg() }),
    output: { name: "voz.mp3", mime: "audio/mpeg" } },
];

for (const tool of SERVER_TOOLS) {
  test(`${tool.slug}: subida tus con sus metadatos, opciones del Anexo A, eventos del trabajo y descarga firmada`, async ({ page }) => {
    const input = await tool.input();
    const body = Buffer.from(`resultado de ${tool.slug}`);
    const server = await mockServer(page, { ...tool.output, body });
    const { link, download } = await runServerTool(page, tool.slug, [input]);
    expect(server.metadata).toEqual([{ filename: input.name, tool: tool.slug }]);
    expect(server.uploadedBytes).toBe(input.buffer.length);
    expect(server.jobs).toEqual([{ tool: tool.slug, upload_ids: ["subida1"], options: defaults(tool.slug) }]);
    await expect(link).toHaveAttribute("download", tool.output.name);
    expect(download.equals(body)).toBe(true);
  });
}

function jwt(): string {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "EdDSA" })}.${part({ sub: "u-e2e", exp: Math.floor(Date.now() / 1000) + 900 })}.firma`;
}

test("pase de 24 h con el pago de prueba: pedido → captura → pase activo y factura en la cuenta (D-273)", async ({ page }) => {
  await page.route("**/api/auth/get-session**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    user: { id: "u-e2e", email: "ana@ejemplo.test", name: "Ana", emailVerified: true },
    session: { id: "s1", userId: "u-e2e", expiresAt: new Date(Date.now() + 86_400_000).toISOString() } }) }));
  await page.route("**/api/auth/token**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: jwt() }) }));
  let order: unknown = null;
  let paid = false;
  const until = new Date(Date.now() + 86_400_000).toISOString();
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    const json = (data: unknown) => route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (url.pathname === "/v1/billing/config") {
      return json({ provider: "fake", client_id: "", env: "sandbox", currency: "EUR", price_cents: 100, base_cents: 83, vat_cents: 17,
        vat_rate_bp: 2100, hours: 24, required: true });
    }
    if (url.pathname === "/v1/billing/pass") return json({ active: paid, expires_at: paid ? until : null, unlimited: false });
    if (req.method() === "POST" && url.pathname === "/v1/billing/orders") {
      expect(req.headers()["authorization"]).toMatch(/^Bearer .+\..+\..+$/);
      order = req.postDataJSON();
      return json({ order_id: "0b5c0a3e-0000-4000-8000-000000000001", provider_order_id: "FAKE-1" });
    }
    if (req.method() === "POST" && url.pathname === "/v1/billing/orders/0b5c0a3e-0000-4000-8000-000000000001/capture") {
      paid = true;
      return json({ status: "paid", pass_until: until });
    }
    if (url.pathname === "/v1/billing/orders") {
      return json({ orders: paid ? [{ id: "o1", status: "paid", hours: 24, total_cents: 100, created_at: until, paid_at: until, refunded_at: null }] : [] });
    }
    if (url.pathname === "/v1/billing/invoices") {
      return json({ invoices: paid ? [{ id: "i1", number: "S2026-000001", kind: "F2", issued_at: until, total_cents: 100, rectifies_id: null }] : [] });
    }
    if (url.pathname === "/v1/billing/profile") return json({ name: "", tax_id: "", address: "", postal_code: "", city: "", country: "ES", complete: false });
    if (url.pathname === "/v1/me") return json({ user_id: "u-e2e", plan: paid ? "pro" : "free", email: "ana@ejemplo.test" });
    if (url.pathname === "/v1/me/usage") return json({ light: { used: 0, limit: 50 }, heavy: { used: 0, limit: 200 } });
    if (url.pathname === "/v1/me/jobs") return json({ jobs: [] });
    return route.fulfill({ status: 404, headers: cors });
  });

  await page.goto("/es/precios");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("1 €");
  await page.getByRole("link", { name: "Conseguir el pase" }).click();
  await page.waitForURL(/\/es\/pase/);
  const pay = page.getByRole("button", { name: /Pagar 1 €/ });
  await pay.click();
  await expect(page.locator(".checkout-error")).toHaveText("Marca la casilla para continuar.");
  expect(order).toBeNull();
  await page.locator("[data-pass-waiver]").check();
  await pay.click();
  await expect(page.locator("[data-pass-paid]")).toContainText("Tu pase está activo hasta");
  expect(order).toEqual({ locale: "es", waiver: true });
  await page.getByRole("link", { name: "Ver la factura" }).click();
  await page.waitForURL(/\/es\/cuenta/);
  await expect(page.locator('[data-pass-state="active"]')).toBeVisible();
  await expect(page.getByRole("cell", { name: "S2026-000001" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Descargar PDF" })).toBeVisible();
});

test("herramienta avanzada sin pase: ofrece el pase antes de subir nada (D-273)", async ({ page }) => {
  let uploads = 0;
  await page.route(`${UP}/**`, (route) => { uploads += 1; return route.fulfill({ status: 500, headers: cors }); });
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (url.pathname === "/v1/billing/config") {
      return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify({
        provider: "fake", client_id: "", env: "sandbox", currency: "EUR", price_cents: 100, base_cents: 83, vat_cents: 17, vat_rate_bp: 2100,
        hours: 24, required: true }) });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.goto("/es/pdf-a-word");
  await expect(page.getByRole("note").filter({ hasText: "Herramienta avanzada" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({ name: "carta.pdf", mimeType: "application/pdf", buffer: await pdf(1) });
  await page.getByRole("button", { name: "Empezar" }).click();
  const offer = page.locator("[data-pass-offer]");
  await expect(offer).toBeVisible();
  await expect(offer.getByRole("link", { name: "Crear cuenta y conseguir el pase" })).toHaveAttribute("href", /\/es\/registro\?volver=/);
  expect(uploads).toBe(0);
});
