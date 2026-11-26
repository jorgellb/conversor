import { expect, test } from "@playwright/test";

// D-269: la herramienta y la valoración vienen ya en el HTML inicial del servidor, en su sitio, sin límites de Suspense
// que React 19.2 saque aparte y muestre hasta 300 ms después del primer pintado (el artículo de debajo bajaba de golpe y
// Lighthouse daba CLS de 0,4 a 0,55 en las páginas de herramienta).
for (const path of ["/es/comprimir-pdf", "/es/resumir-pdf", "/en/compress-pdf"]) {
  test(`HTML inicial completo en ${path}`, async ({ request }) => {
    const html = await (await request.get(path)).text();
    const article = html.indexOf("<article");
    expect(article).toBeGreaterThan(0);
    expect(html).not.toMatch(/<template id="B:\d+"/);
    const tool = html.indexOf('type="file"');
    expect(tool).toBeGreaterThan(0);
    expect(tool).toBeLessThan(article);
  });
}
