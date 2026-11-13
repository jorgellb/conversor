import { defineConfig } from "@playwright/test";

/**
 * Proyectos (16.1):
 * - navegador: herramientas de navegador contra `next start`; comprueba que el archivo no sale a la red.
 * - servidor: sistema completo con `docker compose up` (tus, API, workers, descargas y pago falso).
 */
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    trace: "retain-on-failure",
    acceptDownloads: true,
    // Navegador ya instalado en el sistema (opcional); en la CI se usa el de `npx playwright install`.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: "navegador", testMatch: /(navegador|editor|f2|f3|f5)\.spec\.ts/, use: { baseURL: process.env.WEB_URL ?? "http://127.0.0.1:3100" } },
    { name: "servidor", testMatch: /servidor\.spec\.ts/, use: { baseURL: process.env.WEB_URL ?? "http://localhost:3000" } },
  ],
});
