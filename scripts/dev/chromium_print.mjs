// Ayudante de scripts/dev/gotenberg_local.py (solo desarrollo): imprime o captura una página con el Chromium de
// Playwright, con las opciones de Gotenberg ya traducidas. Uso: node chromium_print.mjs <trabajo.json>
// La página local solo puede cargar archivos de su carpeta (como el Chromium de `gotenberg`, sin red); una URL sí sale.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

const job = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const o = job.options;
const browser = await chromium.launch();
let failed = false;
try {
  const context = await browser.newContext({ viewport: { width: Number(o.width) || 1280, height: Number(o.height) || 720 } });
  const page = await context.newPage();
  const base = pathToFileURL(job.dir + "/").href;
  if (!job.url) {
    await page.route("**/*", (route) => (route.request().url().startsWith(base) || route.request().url().startsWith("data:")
      ? route.continue() : route.abort()));
  }
  page.on("pageerror", () => { failed = true; });
  if (o.emulatedMediaType) await page.emulateMedia({ media: o.emulatedMediaType });
  await page.goto(job.url || `${base}index.html`, { waitUntil: o.skipNetworkIdleEvent === "true" ? "load" : "networkidle", timeout: 60000 });
  if (o.waitForExpression) await page.waitForFunction(o.waitForExpression, null, { timeout: 30000 });
  if (o.waitDelay) await page.waitForTimeout(Math.min(10000, parseFloat(o.waitDelay) * (/ms$/.test(o.waitDelay) ? 1 : 1000)));
  if (failed && o.failOnConsoleExceptions === "true") process.exit(9);
  const size = (v) => (v === undefined || v === "" ? undefined : /^[\d.]+$/.test(String(v)) ? `${v}in` : String(v));
  if (job.mode === "screenshot") {
    const shot = { path: job.out, type: o.format === "jpeg" ? "jpeg" : "png", fullPage: o.clip !== "true",
      omitBackground: o.omitBackground === "true" };
    if (shot.type === "jpeg" && o.quality) shot.quality = Number(o.quality);
    await page.screenshot(shot);
  } else {
    await page.pdf({
      path: job.out, width: size(o.paperWidth), height: size(o.paperHeight), landscape: o.landscape === "true",
      margin: { top: size(o.marginTop) ?? "0.39in", bottom: size(o.marginBottom) ?? "0.39in", left: size(o.marginLeft) ?? "0.39in",
        right: size(o.marginRight) ?? "0.39in" },
      printBackground: o.printBackground === "true", preferCSSPageSize: o.preferCssPageSize === "true",
      scale: o.scale ? Math.min(2, Math.max(0.1, Number(o.scale))) : 1, pageRanges: o.nativePageRanges || "",
      outline: o.generateDocumentOutline === "true", tagged: o.pdfua === "true" || o.generateTaggedPdf === "true",
    });
  }
} finally {
  await browser.close();
}
