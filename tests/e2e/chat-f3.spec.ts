import { expect, test, type Page, type Route } from "@playwright/test";

// chat-pdf (F3) con el servidor simulado: preparar el documento, preguntar, respuesta por eventos con las páginas, la
// conversación que viaja con la siguiente pregunta y un error del presupuesto. El trabajo real lo prueba pytest
// (tests/test_chat_pdf.py) y, con la pila completa y el LLM falso, servidor.spec.ts.
const WEB = "http://127.0.0.1:3100", API = "http://127.0.0.1:8100", UP = "http://127.0.0.1:8180";
const cors = {
  "Access-Control-Allow-Origin": WEB, "Access-Control-Allow-Methods": "GET, POST, PATCH, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Accept-Language, Tus-Resumable, Upload-Length, Upload-Offset, Upload-Metadata, Upload-Defer-Length, X-Requested-With",
  "Access-Control-Expose-Headers": "Location, Upload-Offset, Upload-Length, Tus-Resumable",
};
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

function jwt(): string {
  const part = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "EdDSA" })}.${part({ sub: "u-e2e", exp: Math.floor(Date.now() / 1000) + 900 })}.firma`;
}

function sse(events: { event: string; data: object }[]): string {
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
}

async function simulate(page: Page, asked: Record<string, unknown>[], chatStatus = 200) {
  await page.route("**/api/auth/get-session**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    user: { id: "u-e2e", email: "ana@ejemplo.test", name: "Ana", emailVerified: true },
    session: { id: "s1", userId: "u-e2e", expiresAt: new Date(Date.now() + 86_400_000).toISOString() } }) }));
  await page.route("**/api/auth/token**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: jwt() }) }));
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
    const json = (status: number, body: unknown) => route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith("/v1/ai/budget")) {
      return json(200, { user: { used: 0, limit: 30, remaining: 30 }, per_task: 20, pages_per_task: 150, available: true, pro_only: false,
        reset_at: "2026-11-06T00:00:00+00:00", reset_local: "01:00", consent_required: true, consent_version: "2026-11-05", tools: { "chat-pdf": true } });
    }
    const job = { id: "c1", tool: "chat-pdf", status: "succeeded", progress: 1, message: null, error: null, expires_at: null,
      inputs: [{ name: "acta.pdf", size: offset }], outputs: [] };
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) return json(201, job);
    if (req.url().endsWith("/v1/jobs/c1")) return json(200, job);  // preparar no deja archivos: la web vuelve a consultarlo
    if (req.url().endsWith("/v1/ai/chat/c1")) return json(200, { job_id: "c1", name: "acta.pdf", pages: [1, 2, 3], tokens: 900, chunks: 0, expires_at: null });
    if (req.method() === "POST" && req.url().endsWith("/v1/ai/chat")) {
      asked.push(req.postDataJSON());
      if (chatStatus !== 200) {
        return json(chatStatus, { error: { code: "AI_BUDGET_EXHAUSTED", message: "Se ha agotado la IA de hoy. Vuelve a partir de las 01:00 (hora de Madrid)." } });
      }
      return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "text/event-stream" }, body: sse([
        { event: "start", data: { id: "m1" } },
        { event: "delta", data: { type: "delta", text: "El contrato vence el " } },
        { event: "delta", data: { type: "delta", text: "31 de marzo de 2027 (pág. 2)." } },
        { event: "done", data: { type: "done", model: "falso/modelo-de-prueba:free", mode: "completo", pages: [2] } },
      ]) });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
}

test("chat-pdf: prepara el documento, responde por trozos con las páginas y manda la conversación", async ({ page }) => {
  const asked: Record<string, unknown>[] = [];
  await simulate(page, asked);
  await page.goto("/es/chat-pdf");
  await expect(page.getByRole("heading", { name: "Chat con PDF" })).toBeVisible();
  const prepare = page.getByRole("button", { name: "Preparar el documento", exact: true });
  await page.locator("[data-chat-file]").setInputFiles({ name: "acta.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(prepare).toBeDisabled();  // falta el consentimiento
  await page.locator("[data-ai-consent]").check();
  await prepare.click();
  await expect(page.locator("[data-chat-ready]")).toContainText("Listo para preguntar sobre «acta.pdf» (páginas 1–3).");
  const input = page.locator("[data-chat-input]");
  await input.fill("¿Cuándo vence el contrato?");
  await input.press("Enter");
  const answer = page.locator('[data-chat-message="assistant"]').last();
  await expect(answer).toContainText("El contrato vence el 31 de marzo de 2027 (pág. 2).");
  await expect(answer.locator("[data-chat-pages]")).toHaveText("Páginas: 2");
  expect(asked[0]).toMatchObject({ job_id: "c1", message: "¿Cuándo vence el contrato?", history: [], ai_consent: true });
  await input.fill("¿Y quién lo firma?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.locator('[data-chat-message="assistant"]')).toHaveCount(2);
  expect(asked[1]).toMatchObject({ history: [
    { role: "user", content: "¿Cuándo vence el contrato?" },
    { role: "assistant", content: "El contrato vence el 31 de marzo de 2027 (pág. 2)." },
  ] });
});

test("chat-pdf: sin presupuesto, la respuesta dice desde qué hora se puede volver", async ({ page }) => {
  const asked: Record<string, unknown>[] = [];
  await simulate(page, asked, 429);
  await page.goto("/es/chat-pdf");
  await page.locator("[data-chat-file]").setInputFiles({ name: "acta.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.locator("[data-ai-consent]").check();
  await page.getByRole("button", { name: "Preparar el documento", exact: true }).click();
  await page.locator("[data-chat-input]").fill("¿De qué trata?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();
  await expect(page.locator('[data-chat-message="assistant"]').getByRole("alert")).toHaveText(/Vuelve a partir de las 01:00/);
});
