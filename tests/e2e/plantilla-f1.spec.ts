import { expect, test, type Page } from "@playwright/test";

// Regresión visual de 16.1: la plantilla de página de herramienta en móvil y en escritorio, con una herramienta de
// navegador (unir-pdf) y una de servidor (comprimir-pdf). Se compara solo la primera pantalla (cabecera, migas, título,
// resumen, zona de archivos y opciones). El contenido propio de 8.2 (<article>) se tapa: lo cambian los lotes de
// contenido y no es parte de la plantilla. Las referencias están en __capturas__ (D-144); se regeneran con
// `npx playwright test -c tests/e2e/playwright.config.ts --project=navegador plantilla-f1 --update-snapshots`.

// La web usa la fuente del sistema (system-ui), distinta en cada máquina; para que la captura no dependa de ella se
// fuerza la Noto Sans que sirve la propia web en /fonts (la misma en local y en la CI).
const SAME_FONT = `*, *::before, *::after { font-family: "NotoSansEditor", sans-serif !important; }`;

async function openTemplate(page: Page, path: string) {
  await page.goto(path);
  await page.addStyleTag({ content: SAME_FONT });
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await expect(page.locator("h1")).toBeVisible();
}

// Siempre el Chromium de Playwright (`npx playwright install chromium`, el mismo que la CI), aunque PW_CHROMIUM_PATH
// apunte a otro: entre versiones de Chrome el suavizado del texto cambia en torno al 2 % de los píxeles.
test.use({ launchOptions: {} });

const PAGES = [
  { name: "unir-pdf", path: "/es/unir-pdf" },
  { name: "comprimir-pdf", path: "/es/comprimir-pdf" },
];

const VIEWPORTS = [
  { name: "movil", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 } },
  { name: "escritorio", use: { viewport: { width: 1280, height: 900 }, isMobile: false, hasTouch: false, deviceScaleFactor: 1 } },
];

for (const vp of VIEWPORTS) {
  test.describe(`plantilla de herramienta en ${vp.name}`, () => {
    test.use({ ...vp.use, colorScheme: "light", locale: "es-ES" });
    for (const p of PAGES) {
      test(`${p.name} (${vp.name})`, async ({ page }) => {
        await openTemplate(page, p.path);
        // Nada se sale por los lados (en móvil, la cabecera pasa a dos líneas).
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await expect(page).toHaveScreenshot(`${p.name}-${vp.name}.png`, { mask: [page.locator("article")] });
      });
    }
  });
}
