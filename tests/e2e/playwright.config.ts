import { defineConfig } from "@playwright/test";

/**
 * Proyectos (16.1):
 * - navegador: herramientas de navegador contra `next start`; comprueba que el archivo no sale a la red.
 * - servidor: sistema completo con `docker compose up` (tus, API, workers, descargas y pago falso).
 * Regresión visual (16.1, D-144): referencias en __capturas__/<archivo>/ sin el sufijo del sistema (local y CI son Linux),
 * con una tolerancia pequeña para el suavizado de texto de cada versión de Chromium.
 */
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  snapshotPathTemplate: "{testDir}/__capturas__/{testFilePath}/{arg}{ext}",
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.005, threshold: 0.2, animations: "disabled", caret: "hide", scale: "css" },
  },
  use: {
    trace: "retain-on-failure",
    acceptDownloads: true,
    // Navegador ya instalado en el sistema (opcional); en la CI se usa el de `npx playwright install`.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: "navegador", testMatch: /(navegador|editor|f1|f2|f3|f4|f5|f6|f7)\.spec\.ts/, use: { baseURL: process.env.WEB_URL ?? "http://127.0.0.1:3100" } },
    { name: "servidor", testMatch: /servidor\.spec\.ts/, use: { baseURL: process.env.WEB_URL ?? "http://localhost:3000" } },
  ],
});
