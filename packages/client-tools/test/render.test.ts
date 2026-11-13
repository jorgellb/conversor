import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { runClientTool, renderScale, stack, toGray, type PdfRenderer, type Raster } from "../src/index";

/** Renderizador falso: cada página es un rectángulo de color de (100 + i) × 50 puntos. */
function fakeRenderer(pages = 3): PdfRenderer {
  return {
    async open() {
      return {
        pageCount: pages,
        pageSize: (i) => ({ width: 100 + i, height: 50 }),
        async render(i, scale): Promise<Raster> {
          const width = Math.round((100 + i) * scale);
          const height = Math.round(50 * scale);
          const data = new Uint8ClampedArray(width * height * 4);
          for (let p = 0; p < data.length; p += 4) data.set([200, 100, 50, 255], p);
          return { width, height, data };
        },
        close() {},
      };
    },
  };
}

const encoder = async (img: Raster, format: string) => new TextEncoder().encode(`${format}:${img.width}x${img.height}:${img.data[0]}`);
const OPTS = { formato: "jpg", color: "color", dpi: 144, calidad: 85, paginas: "todas", salida: "una_por_pagina", organizacion: "carpeta_por_archivo" };

describe("pdf-a-jpg / pdf-a-png", () => {
  it("una imagen por página, con rango y nombres como el servidor", async () => {
    const res = await runClientTool("pdf-a-jpg", [{ name: "texto.pdf", bytes: new Uint8Array() }], { ...OPTS, paginas: "1, 3" },
      { renderer: fakeRenderer(), encoder });
    const zip = unzipSync(res.outputs[0].bytes);
    expect(Object.keys(zip).sort()).toEqual(["texto-1.jpg", "texto-3.jpg"]);
    expect(new TextDecoder().decode(zip["texto-3.jpg"])).toBe("jpg:204x100:200");
  });

  it("una sola página da una imagen suelta, en gris", async () => {
    const res = await runClientTool("pdf-a-png", [{ name: "a.pdf", bytes: new Uint8Array() }], { ...OPTS, paginas: "2", color: "gris" },
      { renderer: fakeRenderer(), encoder });
    expect(res.outputs[0].name).toBe("a-2.png");
    const gray = Math.round(0.299 * 200 + 0.587 * 100 + 0.114 * 50);
    expect(new TextDecoder().decode(res.outputs[0].bytes)).toBe(`png:202x100:${gray}`);
  });

  it("varios PDF en carpetas, y una sola imagen apilada", async () => {
    const files = [{ name: "a.pdf", bytes: new Uint8Array() }, { name: "b.pdf", bytes: new Uint8Array() }];
    const res = await runClientTool("pdf-a-imagenes", files, { ...OPTS, formato: "webp", paginas: "1" }, { renderer: fakeRenderer(), encoder });
    expect(Object.keys(unzipSync(res.outputs[0].bytes)).sort()).toEqual(["a/a-1.webp", "b/b-1.webp"]);
    const one = await runClientTool("pdf-a-png", [files[0]], { ...OPTS, salida: "una_sola", dpi: 72 }, { renderer: fakeRenderer(), encoder });
    // La primera página (100 px) queda centrada en 102 px: el píxel (0, 0) es el fondo blanco.
    expect(new TextDecoder().decode(one.outputs[0].bytes)).toBe("png:102x150:255");
  });

  it("pdf-a-webp fuerza WEBP y CMYK no se hace en el navegador", async () => {
    const res = await runClientTool("pdf-a-webp", [{ name: "a.pdf", bytes: new Uint8Array() }], { ...OPTS, formato: "jpg", paginas: "1" },
      { renderer: fakeRenderer(), encoder });
    expect(res.outputs[0].name).toBe("a-1.webp");
    await expect(runClientTool("pdf-a-jpg", [{ name: "a.pdf", bytes: new Uint8Array() }], { ...OPTS, color: "cmyk" },
      { renderer: fakeRenderer(), encoder })).rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
  });

  it("limita los píxeles por página y por imagen apilada", () => {
    const s = renderScale({ width: 595, height: 842 }, 600, 1_000_000);
    expect(595 * s * 842 * s).toBeLessThanOrEqual(1_000_001);
    const tile = { width: 10, height: 10, data: new Uint8ClampedArray(400).map((_, i) => (i % 4 === 3 ? 255 : 0)) };
    expect(() => stack([tile, tile], 150)).toThrow();
    expect(toGray(tile, 128).data[0]).toBe(0);
  });
});
