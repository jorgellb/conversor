import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// F4, lote E1: crear-factura en el navegador (encendida en la CI con INVOICING_ES_ENABLED y TOOL_CREAR_FACTURA_ENABLED).
// Totales en vivo con recargo e IRPF, validación del NIF y del IBAN, PDF sin subir nada y el emisor recordado. El cálculo
// y el PDF los prueba Vitest (packages/client-tools/test/invoice.test.ts).

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test("crear-factura: totales en vivo, validación y PDF sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/crear-factura");
  await expect(page.getByRole("heading", { level: 1, name: "Crear factura" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Veri*factu");
  const issuer = page.locator("[data-party='issuer']");
  await issuer.getByLabel("Nombre o razón social").fill("Estudio Pérez, S.L.");
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345675");
  await issuer.getByLabel("Dirección").fill("Calle Mayor 1");
  await issuer.getByLabel("Población").fill("Madrid");
  const customer = page.locator("[data-party='customer']");
  await customer.getByLabel("Nombre o razón social").fill("Ana García");
  await customer.getByLabel(/NIF, NIE o CIF/).fill("12345678Z");
  const line = page.locator("[data-line='0']");
  await line.getByLabel("Descripción").fill("Diseño de logotipo");
  await line.getByLabel("Precio sin IVA").fill("450");
  await page.getByRole("button", { name: "Añadir concepto" }).click();
  const second = page.locator("[data-line='1']");
  await second.getByLabel("Descripción").fill("Libro técnico");
  await second.getByLabel("Cantidad").fill("2");
  await second.getByLabel("Precio sin IVA").fill("19,95");
  await second.locator("select").selectOption("4");
  // Quitar un concepto intermedio no deja cifras de otro en los campos (revisión de F4-E1).
  await page.getByRole("button", { name: "Añadir concepto" }).click();
  const third = page.locator("[data-line='2']");
  await third.getByLabel("Descripción").fill("Sobra");
  await third.getByLabel("Precio sin IVA").fill("999");
  await page.getByRole("button", { name: "Quitar el concepto 2" }).click();
  await expect(page.locator("[data-line='1']").getByLabel("Descripción")).toHaveValue("Sobra");
  await expect(page.locator("[data-line='1']").getByLabel("Precio sin IVA")).toHaveValue("999");
  await page.getByRole("button", { name: "Quitar el concepto 2" }).click();
  await page.getByRole("button", { name: "Añadir concepto" }).click();
  const second2 = page.locator("[data-line='1']");
  await second2.getByLabel("Descripción").fill("Libro técnico");
  await second2.getByLabel("Cantidad").fill("2");
  await second2.getByLabel("Precio sin IVA").fill("19,95");
  await second2.locator("select").selectOption("4");
  const preview = page.locator("[data-invoice-preview]");
  await expect(preview.locator("[data-total]")).toHaveText("586,00 €");
  await page.getByLabel(/Recargo de equivalencia/).check();
  await page.getByLabel("Retención de IRPF").selectOption("15");
  await expect(preview).toContainText("Recargo 5,2 %");
  await expect(preview.locator("[data-payable]")).toHaveText("536,11 €");
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1333");
  await page.getByRole("button", { name: "Generar el PDF" }).click();
  await expect(page.getByText("Tu NIF, NIE o CIF no es válido.")).toBeVisible();
  await expect(page.getByText("El IBAN no es válido.").first()).toBeVisible();
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345674");
  await page.getByLabel("IBAN").fill("ES91 2100 0418 4502 0005 1332");
  await page.getByRole("button", { name: "Generar el PDF" }).click();
  const link = page.getByRole("link", { name: /Descargar factura-/ });
  await expect(link).toBeVisible();
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(d.suggestedFilename()).toMatch(/^factura-\d{4}-0001\.pdf$/);
  expect(readFileSync(await d.path()).subarray(0, 5).toString()).toBe("%PDF-");
  expect(sent).toEqual([]);
  // El emisor y el número siguiente se recuerdan en este navegador.
  await page.reload();
  await expect(page.locator("[data-party='issuer']").getByLabel("Nombre o razón social")).toHaveValue("Estudio Pérez, S.L.");
  await expect(page.getByLabel("Número de factura")).toHaveValue(/\d{4}\/0002$/);
  await expect(page.locator("[data-party='customer']").getByLabel("Clientes guardados en este navegador")).toBeVisible();
});

// F4-E2: «Convertir en factura electrónica» lleva la factura a crear-factura-electronica, que la genera en el servidor
// (API simulada; la generación y KoSIT los prueba pytest en tests/test_facturas_crear.py).
test("crear-factura-electronica: llega desde crear-factura y manda la factura EN 16931 al servidor", async ({ page }) => {
  const API = "http://127.0.0.1:8100";
  const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3100", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Accept-Language" };
  await page.route("https://challenges.cloudflare.com/**", (route) => route.fulfill({ status: 200, contentType: "text/javascript",
    body: "window.turnstile={render:function(el,o){setTimeout(function(){o.callback('ok')},0);return 't1'},remove:function(){}};" }));
  const jobs: Record<string, unknown>[] = [];
  await page.route(`${API}/**`, (route) => {
    const req = route.request();
    const json = (status: number, body: unknown) => route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith("/v1/session/anon")) return json(200, { token: "anon.e2e.firma", expires_in: 86400 });
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) {
      jobs.push(req.postDataJSON());
      return json(201, { id: "e1", tool: "crear-factura-electronica", status: "succeeded", progress: 1, message: null, error: null, expires_at: null, inputs: [],
        outputs: [{ name: "factura-2026-0001.xml", size: 3000, mime: "application/xml", note: "Validada con KoSIT (EN 16931 (UBL)): sin errores.",
          url: "http://127.0.0.1:8190/d/e1/factura-2026-0001.xml?t=x", url_expires_in: 900 }] });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.goto("/es/crear-factura");
  const issuer = page.locator("[data-party='issuer']");
  await issuer.getByLabel("Nombre o razón social").fill("Estudio Pérez, S.L.");
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345674");
  await issuer.getByLabel("Dirección").fill("Calle Mayor 1");
  await issuer.getByLabel("Población").fill("Madrid");
  await page.locator("[data-party='customer']").getByLabel("Nombre o razón social").fill("Cliente S.A.");
  await page.locator("[data-party='customer']").getByLabel(/NIF, NIE o CIF/).fill("A58818501");
  await page.locator("[data-line='0']").getByLabel("Descripción").fill("Consultoría");
  await page.locator("[data-line='0']").getByLabel("Precio sin IVA").fill("1.200");
  await page.getByRole("link", { name: "Convertir en factura electrónica" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Crear factura electrónica" })).toBeVisible();
  await expect(page.locator("[data-party='issuer']").getByLabel("Nombre o razón social")).toHaveValue("Estudio Pérez, S.L.");
  await expect(page.locator("[data-line='0']").getByLabel("Descripción")).toHaveValue("Consultoría");
  await page.locator("[data-einvoice-format]").getByLabel("Formato").selectOption("ubl");
  await page.getByRole("button", { name: "Generar y validar la factura electrónica" }).click();
  await expect(page.getByText("Validada con KoSIT (EN 16931 (UBL)): sin errores.")).toBeVisible();
  await expect(page.locator("[data-einvoice-output]")).toHaveText("Descargar factura-2026-0001.xml");
  expect(jobs).toHaveLength(1);
  const options = jobs[0].options as { formato: string; factura: { emisor: { nif: string }; lineas: { precio: number; iva: number }[]; numero: string } };
  expect(jobs[0].tool).toBe("crear-factura-electronica");
  expect(options.formato).toBe("ubl");
  expect(options.factura.emisor.nif).toBe("B12345674");
  expect(options.factura.lineas).toEqual([{ descripcion: "Consultoría", cantidad: 1, unidad: "ud", precio: 1200, descuento: 0, iva: 21 }]);
});

// F4-E2b: el Facturae se firma en el navegador con el .p12 (la clave no sale; ni el certificado ni la contraseña se envían).
test("crear-factura-electronica: Facturae firmado con XAdES-EPES en el navegador", async ({ page }) => {
  const API = "http://127.0.0.1:8100", FILES = "http://127.0.0.1:8190";
  const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3100", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Accept-Language" };
  await page.route("https://challenges.cloudflare.com/**", (route) => route.fulfill({ status: 200, contentType: "text/javascript",
    body: "window.turnstile={render:function(el,o){setTimeout(function(){o.callback('ok')},0);return 't1'},remove:function(){}};" }));
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() === "POST") sent.push(r.postData() ?? ""); });
  await page.route(`${FILES}/**`, (route) => route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/xml" },
    body: readFileSync("apps/web/test/fixtures/facturae.xml") }));
  await page.route(`${API}/**`, (route) => {
    const req = route.request();
    const json = (status: number, body: unknown) => route.fulfill({ status, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (req.url().endsWith("/v1/session/anon")) return json(200, { token: "anon.e2e.firma", expires_in: 86400 });
    if (req.method() === "POST" && req.url().endsWith("/v1/jobs")) {
      return json(201, { id: "e2", tool: "crear-factura-electronica", status: "succeeded", progress: 1, message: null, error: null, expires_at: null, inputs: [],
        outputs: [{ name: "factura-0042.xml", size: 3000, mime: "application/xml", note: "Cumple el XSD oficial de Facturae 3.2.2.",
          url: `${FILES}/d/e2/factura-0042.xml?t=x`, url_expires_in: 900 }] });
    }
    return route.fulfill({ status: 404, headers: cors });
  });
  await page.goto("/es/crear-factura-electronica");
  const issuer = page.locator("[data-party='issuer']");
  await issuer.getByLabel("Nombre o razón social").fill("Estudio Pérez, S.L.");
  await issuer.getByLabel("NIF, NIE o CIF", { exact: true }).fill("B12345674");
  await issuer.getByLabel("Dirección", { exact: true }).fill("Calle Mayor 1");
  await issuer.getByLabel("Población").fill("Madrid");
  await page.locator("[data-party='customer']").getByLabel("Nombre o razón social").fill("Cliente S.A.");
  await page.locator("[data-party='customer']").getByLabel(/NIF, NIE o CIF/).fill("A58818501");
  await page.locator("[data-line='0']").getByLabel("Descripción").fill("Consultoría");
  await page.locator("[data-line='0']").getByLabel("Precio sin IVA").fill("100");
  await page.locator("[data-einvoice-format]").getByLabel("Formato").selectOption("facturae");
  await page.getByRole("button", { name: "Generar y validar la factura electrónica" }).click();
  const panel = page.locator("[data-facturae-sign]");
  await expect(panel).toBeVisible();
  await panel.getByLabel("Certificado (.p12 o .pfx)").setInputFiles("apps/web/test/fixtures/rsa.p12");
  await panel.getByLabel("Contraseña del certificado").fill("mala");
  await panel.getByRole("button", { name: "Firmar" }).click();
  await expect(panel.getByRole("alert")).toHaveText("La contraseña del certificado no es correcta.");
  await panel.getByLabel("Contraseña del certificado").fill("clave");
  await panel.getByRole("button", { name: "Firmar" }).click();
  const link = page.locator("[data-facturae-signed]");
  await expect(link).toHaveText("Descargar factura-0042-firmada.xml");
  const [d] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const xml = readFileSync(await d.path(), "utf8");
  expect(xml).toContain("politica_de_firma_formato_facturae_v3_1.pdf");
  expect(xml).toContain("<xades:ClaimedRole>emisor</xades:ClaimedRole>");
  expect(sent.some((body) => body.includes("clave"))).toBe(false); // la contraseña no viaja
});
