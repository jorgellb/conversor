import { expect, test } from "@playwright/test";

// D-271: cada categoría tiene su apartado en el menú y la portada ya no lista todas las herramientas.
test("el menú lleva a cada apartado y el apartado lista y filtra sus herramientas", async ({ page }) => {
  await page.goto("/es");
  const menu = page.getByRole("navigation", { name: "Categorías" });
  await expect(menu.getByRole("link")).toHaveCount(10);
  // La portada enseña las más usadas y las categorías, no las 300 herramientas.
  expect(await page.locator("main a[href^='/es/']").count()).toBeLessThan(40);

  await menu.getByRole("link", { name: "PDF", exact: true }).click();
  await expect(page).toHaveURL(/\/es\/herramientas-pdf$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Herramientas PDF");
  await expect(menu.getByRole("link", { name: "PDF", exact: true })).toHaveAttribute("aria-current", "page");
  const cards = page.locator("main li.tool-card");
  const total = await cards.count();
  expect(total).toBeGreaterThan(40);

  await page.getByRole("searchbox").fill("comprimir");
  await expect(cards.filter({ visible: true })).not.toHaveCount(total);
  await expect(page.getByRole("link", { name: /Comprimir PDF/ })).toBeVisible();
  await page.getByRole("searchbox").fill("zzzz-nada");
  await expect(page.getByRole("status")).toBeVisible();
});

test("las migas de una herramienta llevan a su apartado, y el idioma al apartado equivalente", async ({ page }) => {
  await page.goto("/es/comprimir-pdf");
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "PDF" }).click();
  await expect(page).toHaveURL(/\/es\/herramientas-pdf$/);
  await page.goto("/es/herramientas-3d");
  await page.getByRole("link", { name: "English" }).click();
  await expect(page).toHaveURL(/\/en\/3d-tools$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3D tools");
});

test("en móvil la barra de categorías no saca la página por los lados", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 360, height: 780 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.goto("/es/herramientas-datos");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await ctx.close();
});
