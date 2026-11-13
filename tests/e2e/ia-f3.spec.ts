import { expect, test, type Page, type Route } from "@playwright/test";

// IA (F3) con el servidor simulado: cuenta, aviso de 6.6 con casilla obligatoria, peticiones que quedan y «no disponible
// temporalmente». El trabajo real (proveedor falso, reservas y caché) lo prueba pytest (tests/test_ia.py).
const WEB = "http://127.0.0.1:3100", API = "http://127.0.0.1:8100", UP = "http://127.0.0.1:8180", FILES = "http://127.0.0.1:8190";
const cors = {
  "Access-Control-Allow-Origin": WEB, "Access-Control-Allow-Methods": "GET, POST, PATCH, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept-Language, Tus-Resumable, Upload-Length, Upload-Offset, Upload-Metadata, Upload-Defer-Length, X-Requested-With",
  "Access-Control-Expose-Headers": "Location, Upload-Offset, Upload-Length, Tus-Resumable",
};
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

function jwt(): string {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "EdDSA" })}.${part({ sub: "u-e2e", exp: Math.floor(Date.now() / 1000) + 900 })}.firma`;
}

async function signedIn(page: Page) {
  await page.route("**/api/auth/get-session**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    user: { id: "u-e2e", email: "ana@ejemplo.test", name: "Ana", emailVerified: true },
    session: { id: "s1", userId: "u-e2e", expiresAt: new Date(Date.now() + 86_400_000).toISOString() } }) }));
  await page.route("**/api/auth/token**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: jwt() }) }));
}

function budget(tools: Record<string, boolean>, remaining = 3) {
  return { user: { used: 3 - remaining, limit: 3, remaining }, per_task: 5, pages_per_task: 30, available: true, pro_only: false,
    reset_at: "2026-11-06T00:00:00+00:00", reset_local: "01:00", consent_required: true, consent_version: "2026-11-05", tools };
}

test("resumir-pdf: sin cuenta pide iniciar sesión; con cuenta, el aviso es obligatorio y viaja con el trabajo", async ({ page }) => {
  await page.goto("/es/resumir-pdf");
  await expect(page.getByRole("heading", { name: "Resumir PDF" })).toBeVisible();
  const panel = page.locator("[data-ai-panel]");
  await expect(panel).toContainText("Herramienta de IA en pruebas, sujeta a disponibilidad diaria.");
  await expect(panel).toContainText("Las herramientas de IA necesitan una cuenta gratuita.");
  await expect(panel.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/es/entrar");

  await signedIn(page);
  let created: Record<string, unknown> = {};
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
  await page.route(`${API}/**`, (route: Route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith("/v1/ai/budget")) {
      return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(budget({ "resumir-pdf": true })) });
    }
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) {
      created = req.postDataJSON();
      return route.fulfill({ status: 201, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify({
        id: "j1", tool: "resumir-pdf", status: "succeeded", progress: 1, message: null, error: null, expires_at: null,
        inputs: [{ name: "acta.pdf", size: offset }],
        outputs: [{ name: "acta-resumen.docx", size: 10, mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          note: "Peticiones de IA usadas: 1.", url: `${FILES}/d/j1/acta-resumen.docx?t=x`, url_expires_in: 900 }] }) });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.reload();
  await expect(panel).toContainText("Te quedan 3 peticiones de IA hoy; se renuevan a las 01:00 (hora de Madrid).");
  await expect(panel).toContainText("Antes de usar la IA");
  await expect(panel).toContainText("puede estar fuera de la Unión Europea");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "acta.pdf", mimeType: "application/pdf", buffer: PDF });
  const run = page.getByRole("button", { name: "Empezar", exact: true });
  await expect(run).toBeDisabled();  // sin la casilla no se puede empezar
  await panel.locator("[data-ai-consent]").check();
  await expect(run).toBeEnabled();
  await run.click();
  await expect(page.getByRole("link", { name: /acta-resumen\.docx/ }).first()).toBeVisible();
  expect(created).toMatchObject({ tool: "resumir-pdf", upload_ids: ["subida1"], ai_consent: true });
  // El consentimiento vale para el resto de la sesión.
  await page.reload();
  await expect(panel.locator("[data-ai-consent]")).toBeChecked();
});

test("resumir-pdf: sin modelo, «no disponible temporalmente»; sin peticiones, la hora de Madrid", async ({ page }) => {
  await signedIn(page);
  let tools = { "resumir-pdf": false };
  let remaining = 3;
  await page.route(`${API}/**`, (route: Route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(budget(tools, remaining)) });
  });
  await page.goto("/en/summarize-pdf");
  const panel = page.locator("[data-ai-panel]");
  await expect(panel.locator("[data-ai-unavailable]")).toHaveText(/Temporarily unavailable/);
  await page.locator('input[type="file"]').first().setInputFiles({ name: "a.pdf", mimeType: "application/pdf", buffer: PDF });
  await panel.locator("[data-ai-consent]").check();
  await expect(page.getByRole("button", { name: "Start", exact: true })).toBeDisabled();
  tools = { "resumir-pdf": true };
  remaining = 0;
  await page.goto("/es/resumir-pdf");
  await expect(panel).toContainText("Hoy ya no te quedan peticiones de IA. Vuelve a partir de las 01:00 (hora de Madrid).");
});

test("lote B de F3: formularios de preguntas, fichas, presentación y traducción con sus opciones dependientes", async ({ page }) => {
  await page.goto("/es/generador-de-preguntas");
  await expect(page.getByRole("heading", { name: "Generador de preguntas" })).toBeVisible();
  await expect(page.getByLabel("Número de preguntas")).toHaveValue("10");
  await expect(page.getByLabel("Opciones por pregunta")).toBeVisible();
  await page.getByLabel("Tipo de pregunta").selectOption("verdadero_falso");
  await expect(page.getByLabel("Opciones por pregunta")).toHaveCount(0);  // solo con test o mezcla
  await expect(page.getByLabel("Soluciones")).toBeVisible();
  await page.getByLabel("Formato").selectOption("gift");
  await expect(page.getByLabel("Soluciones")).toHaveCount(0);  // Moodle ya lleva las correctas
  await expect(page.locator("[data-ai-panel]")).toContainText("Las herramientas de IA necesitan una cuenta gratuita.");

  await page.goto("/es/pdf-a-fichas");
  await expect(page.getByLabel("Formato").locator("option", { hasText: "Anki o Quizlet (TXT con tabuladores)" })).toHaveCount(1);
  await page.goto("/es/pdf-a-presentacion");
  await expect(page.getByLabel("Notas del orador")).toBeChecked();
  await expect(page.getByLabel("Número de diapositivas (con la portada)")).toHaveValue("10");
  await page.goto("/en/translate-pdf");
  await expect(page.getByRole("heading", { name: "Translate PDF" })).toBeVisible();
  await expect(page.getByLabel("Translate into")).toHaveValue("en");
  await page.getByText("More options").click();
  await expect(page.getByLabel("Terms not to translate (one per line)")).toBeVisible();
});
