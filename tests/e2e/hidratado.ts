import type { Page } from "@playwright/test";

/**
 * Espera a que React haya enganchado el elemento (la página ya hidratada): lo que se escribe o se elige antes se pierde, y
 * con la batería entera en paralelo la hidratación tarda más que el `goto` (D-265).
 */
export async function waitHydrated(page: Page, selector: string, timeout = 30_000): Promise<void> {
  await page.waitForFunction((sel) => {
    const el = document.querySelector(sel);
    return !!el && Object.keys(el).some((k) => k.startsWith("__reactProps"));
  }, selector, { timeout, polling: 50 });
}
