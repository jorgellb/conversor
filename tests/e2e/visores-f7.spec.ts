import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// visor-3d, visor-gcode, comprimir-glb y render-modelo-3d (7.20, F7-H, D-257) en Chromium: WebGL, el worker con Draco y
// el lector de G-code propio, sin subir nada y sin violar la CSP.

function watchUploads(page: Page): string[] {
  const sent: string[] = [];
  page.on("request", (r) => { if (r.method() !== "GET" && r.method() !== "HEAD" && !r.url().includes("/api/auth/")) sent.push(r.url()); });
  return sent;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`));
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().startsWith("CSP")) throw new Error(m.text());
  });
  page.on("pageerror", (err) => { throw err; });
});

const BOX: [number, number, number][] = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
const FACES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]];

/** STL binario de una caja de 20 × 30 × 10 mm. */
function stlBox(): Buffer {
  const scale = [20, 30, 10];
  const buf = Buffer.alloc(84 + FACES.length * 50);
  buf.writeUInt32LE(FACES.length, 80);
  FACES.forEach((f, k) => {
    const at = 84 + k * 50 + 12;
    f.forEach((v, j) => BOX[v].forEach((c, i) => buf.writeFloatLE(c * scale[i], at + j * 12 + i * 4)));
  });
  return buf;
}

/** GLB de una esfera UV (metros, Y arriba) con suficientes vértices para que Draco reduzca el tamaño. */
function sphereGlb(n = 60): Buffer {
  const pos: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    for (let j = 0; j <= n; j++) {
      const th = (i / n) * Math.PI, ph = (j / n) * 2 * Math.PI;
      pos.push(0.05 * Math.sin(th) * Math.cos(ph), 0.05 * Math.cos(th), 0.05 * Math.sin(th) * Math.sin(ph));
    }
  }
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const a = i * (n + 1) + j, b = a + n + 1; idx.push(a, b, a + 1, b, b + 1, a + 1); }
  const p = Buffer.from(new Float32Array(pos).buffer);
  const ix = Buffer.from(new Uint32Array(idx).buffer);
  const bin = Buffer.concat([p, ix]);
  const json = {
    asset: { version: "2.0" }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0, name: "bola" }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1 }] }],
    buffers: [{ byteLength: bin.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: p.length, target: 34962 }, { buffer: 0, byteOffset: p.length, byteLength: ix.length, target: 34963 }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: pos.length / 3, type: "VEC3", min: [-0.05, -0.05, -0.05], max: [0.05, 0.05, 0.05] },
      { bufferView: 1, componentType: 5125, count: idx.length, type: "SCALAR" },
    ],
  };
  let text = Buffer.from(JSON.stringify(json));
  text = Buffer.concat([text, Buffer.alloc((4 - (text.length % 4)) % 4, 0x20)]);
  const head = Buffer.alloc(12);
  head.write("glTF", 0);
  head.writeUInt32LE(2, 4);
  head.writeUInt32LE(12 + 8 + text.length + 8 + bin.length, 8);
  const chunk = (data: Buffer, type: number) => { const h = Buffer.alloc(8); h.writeUInt32LE(data.length, 0); h.writeUInt32LE(type, 4); return Buffer.concat([h, data]); };
  return Buffer.concat([head, chunk(text, 0x4e4f534a), chunk(bin, 0x004e4942)]);
}

/** El lienzo de WebGL tiene algo pintado (no es un color uniforme). */
async function painted(page: Page, selector: string): Promise<number> {
  return page.locator(`${selector} canvas`).evaluate((canvas: HTMLCanvasElement) => {
    const copy = document.createElement("canvas");
    copy.width = 64;
    copy.height = 64;
    const ctx = copy.getContext("2d")!;
    ctx.drawImage(canvas, 0, 0, 64, 64);
    const data = ctx.getImageData(0, 0, 64, 64).data;
    const seen = new Set<number>();
    for (let i = 0; i < data.length; i += 4) seen.add((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]);
    return seen.size;
  });
}

test("visor-3d: abre un STL, mide la caja, corta en sección y guarda una captura sin subir nada", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/visor-3d");
  await page.locator("[data-visor-input]").setInputFiles({ name: "caja.stl", mimeType: "model/stl", buffer: stlBox() });
  await expect(page.locator("[data-visor-size]")).toHaveText("20 mm × 30 mm × 10 mm", { timeout: 30_000 });
  await expect(page.locator("[data-visor-info]")).toContainText("12 triángulos");
  await expect.poll(() => painted(page, "[data-visor-canvas]"), { timeout: 15_000 }).toBeGreaterThan(8);
  await page.locator("[data-visor-section]").selectOption("x");
  await page.getByRole("button", { name: "Arriba" }).click();
  const [shot] = await Promise.all([page.waitForEvent("download"), page.locator("[data-visor-capture]").click()]);
  expect(shot.suggestedFilename()).toBe("caja.png");
  const png = readFileSync(await shot.path());
  expect(png.subarray(1, 4).toString()).toBe("PNG");
  expect(sent).toEqual([]);
});

test("comprimir-glb y visor-3d: el GLB sale con Draco, más pequeño, y el visor lo abre decodificándolo en el worker", async ({ page }) => {
  const sent = watchUploads(page);
  const input = sphereGlb();
  await page.goto("/es/comprimir-glb");
  await page.locator('input[type="file"]').first().setInputFiles({ name: "bola.glb", mimeType: "model/gltf-binary", buffer: input });
  await page.getByRole("button", { name: "Empezar", exact: true }).click();
  await expect(page.getByRole("region", { name: "Resultado" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("region", { name: "Resultado" })).toContainText("menos");
  const link = page.getByRole("link", { name: /bola\.glb/ }).first();
  const [file] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const glb = readFileSync(await file.path());
  expect(glb.subarray(0, 4).toString()).toBe("glTF");
  expect(glb.length).toBeLessThan(input.length / 2);
  expect(glb.toString("latin1")).toContain("KHR_draco_mesh_compression");
  expect(sent).toEqual([]);

  await page.goto("/es/visor-3d");
  await page.locator("[data-visor-input]").setInputFiles({ name: "bola-draco.glb", mimeType: "model/gltf-binary", buffer: glb });
  // glTF en metros: 0,1 m de diámetro son 100 mm.
  await expect(page.locator("[data-visor-size]")).toHaveText(/^100 mm × 100 mm × 100 mm$/, { timeout: 30_000 });
  await expect.poll(() => painted(page, "[data-visor-canvas]"), { timeout: 15_000 }).toBeGreaterThan(8);
  expect(sent).toEqual([]);
});

test("visor-gcode: lee un bgcode de Prusa por capas, con leyenda, desplazamientos y reproducción", async ({ page }) => {
  const sent = watchUploads(page);
  const bgcode = readFileSync(path.join(__dirname, "../../packages/client-tools/test/fixtures/pieza.bgcode"));
  await page.goto("/es/visor-gcode");
  await page.locator("[data-gcode-input]").setInputFiles({ name: "pieza.bgcode", mimeType: "application/octet-stream", buffer: bgcode });
  await expect(page.locator("[data-gcode-layers]")).toContainText("Capa 10 de 10", { timeout: 30_000 });
  await expect(page.locator("[data-gcode-info]")).toContainText("3 min 12 s");
  await expect(page.locator("[data-gcode-info]")).toContainText("PrusaSlicer");
  await expect(page.locator("[data-gcode-legend]")).toContainText("Perímetro exterior");
  await expect.poll(() => painted(page, "[data-gcode-canvas]"), { timeout: 15_000 }).toBeGreaterThan(4);
  await page.locator("[data-gcode-top]").fill("5");
  await expect(page.locator("[data-gcode-layers]")).toContainText("Capa 6 de 10");
  await page.locator("[data-gcode-travels]").check();
  await page.locator("[data-gcode-mode]").selectOption("velocidad");
  await page.locator("[data-gcode-play]").click();
  await expect(page.locator("[data-gcode-layers]")).toContainText("Capa 7 de 10", { timeout: 15_000 });
  expect(sent).toEqual([]);
});

test("visor-gcode: un archivo sin extrusión se explica", async ({ page }) => {
  await page.goto("/es/visor-gcode");
  await page.locator("[data-gcode-input]").setInputFiles({ name: "vacio.gcode", mimeType: "text/plain", buffer: Buffer.from("G28\nG1 X10 Y10\n") });
  await expect(page.locator("[data-gcode-error]")).toContainText("no parece un G-code de impresión", { timeout: 30_000 });
});

test("render-modelo-3d: PNG transparente del tamaño pedido y ZIP con varios modelos", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/render-modelo-3d");
  await page.getByLabel("Tamaño").selectOption("512");
  await page.locator("[data-render-input]").setInputFiles([
    { name: "caja.stl", mimeType: "model/stl", buffer: stlBox() },
    { name: "bola.glb", mimeType: "model/gltf-binary", buffer: sphereGlb(30) },
  ]);
  await page.locator("[data-render-run]").click();
  await expect(page.locator("[data-render-image]")).toHaveCount(2, { timeout: 60_000 });
  const [zip] = await Promise.all([page.waitForEvent("download"), page.locator("[data-render-zip]").click()]);
  expect(readFileSync(await zip.path()).subarray(0, 2).toString()).toBe("PK");
  const [one] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Descargar caja.png" }).click()]);
  const png = readFileSync(await one.path());
  expect(png.readUInt32BE(16)).toBe(512);
  expect(png.readUInt32BE(20)).toBe(512);
  expect(png[25]).toBe(6); // RGBA: con transparencia
  expect(sent).toEqual([]);
});


/** glTF de texto con un triángulo de 1 × 1 m; el búfer incrustado en `data:` o aparte («modelo.bin»). */
function triangleGltf(embedded: boolean): { gltf: Buffer; bin: Buffer } {
  const bin = Buffer.from(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]).buffer);
  const uri = embedded ? `data:application/octet-stream;base64,${bin.toString("base64")}` : "modelo.bin";
  const json = {
    asset: { version: "2.0" }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }], meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }],
    buffers: [{ byteLength: bin.length, uri }], bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: bin.length }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: "VEC3", min: [0, 0, 0], max: [1, 1, 0] }],
  };
  return { gltf: Buffer.from(JSON.stringify(json)), bin };
}

test("visor-3d: glTF con los datos incrustados, con su .bin aparte y sin él (D-260)", async ({ page }) => {
  const sent = watchUploads(page);
  await page.goto("/es/visor-3d");
  const embedded = triangleGltf(true);
  await page.locator("[data-visor-input]").setInputFiles({ name: "incrustado.gltf", mimeType: "model/gltf+json", buffer: embedded.gltf });
  await expect(page.locator("[data-visor-size]")).toHaveText("1000 mm × 0 mm × 1000 mm", { timeout: 30_000 }); // en español, 1000 sin separador
  const apart = triangleGltf(false);
  await page.locator("[data-visor-input]").setInputFiles([
    { name: "aparte.gltf", mimeType: "model/gltf+json", buffer: apart.gltf },
    { name: "modelo.bin", mimeType: "application/octet-stream", buffer: apart.bin },
  ]);
  await expect(page.locator("[data-visor-info]")).toContainText("aparte.gltf", { timeout: 30_000 });
  await expect(page.locator("[data-visor-info]")).toContainText("1 triángulos");
  await page.locator("[data-visor-input]").setInputFiles({ name: "solo.gltf", mimeType: "model/gltf+json", buffer: apart.gltf });
  await expect(page.locator("[data-visor-error]")).toContainText("modelo.bin", { timeout: 30_000 });
  expect(sent).toEqual([]);
});

test("visor-3d: un PLY sin caras se ve como nube de puntos", async ({ page }) => {
  await page.goto("/es/visor-3d");
  const ply = ["ply", "format ascii 1.0", "element vertex 4", "property float x", "property float y", "property float z", "end_header",
    "0 0 0", "10 0 0", "0 10 0", "0 0 10", ""].join("\n");
  await page.locator("[data-visor-input]").setInputFiles({ name: "escaneo.ply", mimeType: "application/octet-stream", buffer: Buffer.from(ply) });
  await expect(page.locator("[data-visor-info]")).toContainText("4 puntos", { timeout: 30_000 });
});
