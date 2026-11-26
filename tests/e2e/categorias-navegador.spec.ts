import { expect, test } from "@playwright/test";

// D-271: cada categoría tiene su apartado en el menú y la portada ya no lista todas las herramientas.
test("el menú lleva a cada apartado y el apartado lista y filtra sus herramientas", async ({ page }) => {
  await page.goto("/es");
  const menu = page.getByRole("navigation", { name: "Categorías" });
  await expect(menu.getByRole("link")).toHaveCount(10);
  // La portada enseña las más usadas y las categorías con sus secciones (D-272), no las 300 herramientas.
  expect(await page.locator("main a[href^='/es/']").count()).toBeLessThan(100);

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

// D-272: cada categoría del menú tiene su submenú, por secciones.
test("en escritorio el submenú se abre al pasar el ratón y con el teclado", async ({ page }) => {
  await page.setViewportSize({ width: 1360, height: 900 });
  await page.goto("/es");
  const menu = page.getByRole("navigation", { name: "Categorías" });
  await expect(menu.getByRole("link", { name: "PDF a Word" })).toBeHidden();
  await menu.getByRole("link", { name: "PDF", exact: true }).hover();
  await expect(menu.getByText("Convertir desde PDF")).toBeVisible();
  await expect(menu.getByRole("link", { name: "PDF a Word" })).toBeVisible();
  await menu.getByRole("link", { name: "PDF a Word" }).click();
  await expect(page).toHaveURL(/\/es\/pdf-a-word$/);
  await expect(menu.getByRole("link", { name: "PDF a Word" })).toBeHidden();

  const caret = menu.getByRole("button", { name: "Herramientas de: 3D" });
  await caret.focus();
  await page.keyboard.press("Enter");
  await expect(caret).toHaveAttribute("aria-expanded", "true");
  await expect(menu.getByText("Impresión 3D (G-code)")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(caret).toHaveAttribute("aria-expanded", "false");
  await expect(caret).toBeFocused();
  await expect(menu.getByText("Impresión 3D (G-code)")).toBeHidden();
});

test("en móvil el botón Menú abre una hoja con cada categoría como acordeón", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.goto("/es/comprimir-pdf");
  const menu = page.getByRole("navigation", { name: "Categorías" });
  await expect(menu).toBeHidden();
  await page.getByRole("button", { name: "Menú" }).tap();
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: "Herramientas de: Datos" }).tap();
  await expect(menu.getByText("Mapas y GPS")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await menu.getByRole("link", { name: "GPX a KML" }).tap();
  await expect(page).toHaveURL(/\/es\/gpx-a-kml$/);
  await expect(menu).toBeHidden();
  await page.getByRole("button", { name: "Menú" }).tap();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await ctx.close();
});

test("el apartado va por secciones, con un índice que lleva a cada una", async ({ page }) => {
  await page.goto("/es/herramientas-3d");
  const index = page.getByRole("navigation", { name: "Secciones de la categoría" });
  await expect(page.getByRole("heading", { level: 2, name: /CAD: STEP, IGES, DWG/ })).toBeVisible();
  await index.getByRole("link", { name: /Impresión 3D/ }).click();
  await expect(page).toHaveURL(/#gcode$/);
  await expect(page.getByRole("heading", { level: 2, name: /Impresión 3D/ })).toBeInViewport();
  // Al buscar, las secciones sin resultados desaparecen también del índice.
  await page.getByRole("searchbox").fill("gcode");
  await expect(page.getByRole("heading", { level: 2, name: /Convertir mallas/ })).toBeHidden();
  await expect(index.getByRole("link", { name: /Convertir mallas/ })).toBeHidden();
});
