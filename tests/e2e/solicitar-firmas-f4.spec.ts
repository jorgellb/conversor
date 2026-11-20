import { PDFDocument } from "@cantoo/pdf-lib";
import { expect, test, type Page, type Route } from "@playwright/test";

// F4, lote C2: solicitar-firmas con la API simulada. El propietario prepara la solicitud (fase «preparar» y POST
// /v1/signature-requests) y la firmante firma desde la página del enlace (código, firma dibujada o escrita y
// consentimiento). El flujo real lo prueban pytest (tests/test_solicitar_firmas*.py) y, con Mailpit, la CI.
const WEB = "http://127.0.0.1:3100", API = "http://127.0.0.1:8100", UP = "http://127.0.0.1:8180";
const cors = {
  "Access-Control-Allow-Origin": WEB, "Access-Control-Allow-Methods": "GET, POST, PATCH, HEAD, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Accept-Language, Tus-Resumable, Upload-Length, Upload-Offset, Upload-Metadata, Upload-Defer-Length, X-Requested-With",
  "Access-Control-Expose-Headers": "Location, Upload-Offset, Upload-Length, Tus-Resumable",
};
const TOKEN = "t".repeat(43);

function jwt(): string {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "EdDSA" })}.${part({ sub: "u-e2e", exp: Math.floor(Date.now() / 1000) + 900 })}.firma`;
}

/** Turnstile de pruebas: resuelve al momento con «ok». */
async function fakeTurnstile(page: Page) {
  await page.route("https://challenges.cloudflare.com/**", (route) => route.fulfill({ status: 200, contentType: "text/javascript",
    body: "window.turnstile={render:function(el,o){setTimeout(function(){o.callback('ok')},0);return 't1'},remove:function(){}};" }));
}

async function signedIn(page: Page) {
  await page.route("**/api/auth/get-session**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    user: { id: "u-e2e", email: "ana@ejemplo.test", name: "Ana", emailVerified: true },
    session: { id: "s1", userId: "u-e2e", expiresAt: new Date(Date.now() + 86_400_000).toISOString() } }) }));
  await page.route("**/api/auth/token**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: jwt() }) }));
}

async function pdf(): Promise<Buffer> {
  const doc = await PDFDocument.create();
  doc.addPage([595, 842]);
  return Buffer.from(await doc.save());
}

test("solicitar-firmas: prepara el PDF, crea la solicitud en paralelo y la muestra en la lista", async ({ page }) => {
  await signedIn(page);
  await fakeTurnstile(page);
  const sent: { jobs: unknown[]; requests: unknown[] } = { jobs: [], requests: [] };
  let offset = 0;
  await page.route(`${UP}/**`, (route: Route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.method() === "POST") return route.fulfill({ status: 201, headers: { ...cors, Location: `${UP}/files/subida1`, "Tus-Resumable": "1.0.0" } });
    if (req.method() === "PATCH") {
      offset += req.postDataBuffer()?.length ?? 0;
      return route.fulfill({ status: 204, headers: { ...cors, "Upload-Offset": String(offset), "Tus-Resumable": "1.0.0" } });
    }
    return route.fulfill({ status: 200, headers: { ...cors, "Upload-Offset": String(offset), "Upload-Length": String(offset), "Tus-Resumable": "1.0.0" } });
  });
  const requests: unknown[] = [];
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    const json = (status: number, body: unknown) => route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith("/v1/me")) return json(200, { plan: "free", email: "ana@ejemplo.test", type: "user" });
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) {
      sent.jobs.push(req.postDataJSON());
      return json(201, { id: "j1", tool: "solicitar-firmas", status: "succeeded", progress: 1, message: null, error: null, expires_at: null,
        inputs: [{ name: "contrato.pdf", size: offset }],
        outputs: [{ name: "contrato.pdf", size: 900, mime: "application/pdf", note: null, url: `${API}/x`, url_expires_in: 900 }] });
    }
    if (req.url().endsWith("/v1/signature-requests") && req.method() === "POST") {
      const body = req.postDataJSON();
      sent.requests.push(body);
      const view = { id: "r1", document_name: "contrato.pdf", status: "pending", sequential: false, message: body.message, created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 14 * 86_400_000).toISOString(), completed_at: null, files: [],
        signers: body.signers.map((s: { name: string; email: string }, i: number) => ({ id: `s${i}`, ...s, status: "invited", signed_at: null, invited_at: null })) };
      requests.push(view);
      return json(201, view);
    }
    if (req.url().endsWith("/v1/signature-requests")) return json(200, { requests });
    return route.fulfill({ status: 404, headers: cors });
  });

  await page.goto("/es/solicitar-firmas");
  await expect(page.getByRole("heading", { level: 1, name: "Solicitar firmas" })).toBeVisible();
  await expect(page.getByText("Todavía no has pedido ninguna firma.")).toBeVisible();
  await page.getByLabel("Documento PDF").setInputFiles({ name: "contrato.pdf", mimeType: "application/pdf", buffer: await pdf() });
  const first = page.locator("[data-signer='0']");
  await first.getByLabel("Nombre").fill("  Luis   Gómez ");
  await first.getByLabel("Correo").fill("Luis@Ejemplo.test");
  await page.getByRole("button", { name: "Añadir firmante" }).click();
  const second = page.locator("[data-signer='1']");
  await second.getByLabel("Nombre").fill("Eva");
  await second.getByLabel("Correo").fill("luis@ejemplo.test");
  await page.getByRole("button", { name: "Preparar y enviar las invitaciones" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("Cada firmante necesita un correo distinto.");
  await second.getByLabel("Correo").fill("eva@ejemplo.test");
  await page.getByRole("radio", { name: /En paralelo/ }).check();
  await page.getByLabel("Mensaje para los firmantes (opcional)").fill("Firmad antes del viernes");
  // Con la cuenta gratuita, hasta 3 firmantes.
  await page.getByRole("button", { name: "Añadir firmante" }).click();
  await expect(page.getByRole("button", { name: "Añadir firmante" })).toBeDisabled();
  await page.locator("[data-signer='2']").getByRole("button", { name: "Quitar" }).click();
  await page.getByRole("button", { name: "Preparar y enviar las invitaciones" }).click();
  await expect(page.getByRole("status")).toContainText("Solicitud de «contrato.pdf» creada");
  expect(sent.jobs).toEqual([{ tool: "solicitar-firmas", upload_ids: ["subida1"], options: { firmantes: [{ nombre: "Luis Gómez", campo: "" }, { nombre: "Eva", campo: "" }] } }]);
  expect(sent.requests).toEqual([{ job_id: "j1", position: 0, signers: [{ name: "Luis Gómez", email: "luis@ejemplo.test" }, { name: "Eva", email: "eva@ejemplo.test" }],
    sequential: false, message: "Firmad antes del viernes", days: 14, locale: "es", turnstile_token: "ok" }]);
  const card = page.locator("[data-request='r1']");
  await expect(card).toContainText("Esperando firmas");
  await expect(card).toContainText("Luis Gómez <luis@ejemplo.test> — invitado");
  await expect(card.getByRole("button", { name: "Enviar recordatorio" })).toBeVisible();
});

test("firmar-documento: pide el código, firma con la firma escrita y espera a los demás", async ({ page }) => {
  await fakeTurnstile(page);
  const posted: Record<string, unknown>[] = [];
  let state: "start" | "code" | "signed" = "start";
  const view = () => ({
    request: { document_name: "contrato.pdf", owner_email: "pide@ejemplo.test", message: "Gracias", status: "pending", sequential: true,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(), locale: "es" },
    signer: { name: "Eva", email: "eva@ejemplo.test", status: state === "signed" ? "signed" : "invited", signed_at: null,
      can_sign: state !== "signed", code_sent: state === "code" },
    signers: [{ name: "Luis", status: "signed", me: false }, { name: "Eva", status: state === "signed" ? "signed" : "invited", me: true }],
    consent: "Acepto firmar electrónicamente «contrato.pdf» y que el sello de la plataforma acredite mi firma, la fecha y mi correo.",
    document_url: "http://127.0.0.1:8190/r/x/contrato.pdf?t=" + TOKEN, files: [],
  });
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    const json = (status: number, body: unknown) => route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith(`/v1/sign/${TOKEN}/code`)) { state = "code"; return json(200, { sent: true }); }
    if (req.url().endsWith(`/v1/sign/${TOKEN}`) && req.method() === "POST") {
      const body = req.postDataJSON();
      posted.push(body);
      if (body.code !== "123456") return json(422, { error: { code: "INVALID_OPTIONS", message: "El código no es correcto.", attempts_left: 4 } });
      state = "signed";
      return json(200, view());
    }
    if (req.url().endsWith(`/v1/sign/${TOKEN}`)) return json(200, view());
    return route.fulfill({ status: 404, headers: cors });
  });

  await page.goto(`/es/firmar-documento#${TOKEN}`);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.getByRole("heading", { level: 1, name: "Firmar un documento" })).toBeVisible();
  await expect(page.getByText("pide@ejemplo.test te pide que firmes este documento, Eva.")).toBeVisible();
  await expect(page.getByText("Luis — firmado")).toBeVisible();
  const sign = page.getByRole("button", { name: "Firmar", exact: true });
  await expect(sign).toBeDisabled();
  await page.getByRole("button", { name: "Enviar el código" }).click();
  await expect(page.getByText("Revisa tu correo")).toBeVisible();
  await page.getByLabel("Código").fill("12a3456");
  await expect(page.getByLabel("Código")).toHaveValue("123456");
  await page.getByRole("button", { name: "Dibujar o escribir la firma" }).click();
  const dialog = page.getByRole("dialog", { name: "Firma" });
  await dialog.getByRole("tab", { name: "Escribir" }).click();
  await dialog.getByLabel("Tu nombre").fill("Eva Martín");
  await dialog.getByRole("button", { name: "Usar la firma" }).click();
  await expect(page.getByRole("img", { name: "Tu firma" })).toBeVisible();
  await expect(sign).toBeDisabled();  // falta el consentimiento
  await page.getByRole("checkbox", { name: /Acepto firmar electrónicamente/ }).check();
  await sign.click();
  await expect(page.getByText("Ya has firmado. Recibirás el documento firmado por correo cuando firmen todos.")).toBeVisible();
  expect(posted).toHaveLength(1);
  expect(posted[0].code).toBe("123456");
  expect(posted[0].consent).toBe(true);
  expect(String(posted[0].image)).toMatch(/^data:image\/png;base64,/);
});

test("firmar-documento: sin token en el enlace lo explica", async ({ page }) => {
  await page.goto("/en/sign-document");
  await expect(page.getByText("This link is incomplete: open it from the email you received.")).toBeVisible();
});
