// mermaid-a-svg y mermaid-a-png (F6-N, D-231): el SVG que dibuja Mermaid en la página, autónomo y pintado con resvg.
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { runClientTool, type ClientEnv } from "../src/index";
import { backgroundOf, standaloneSvg, viewBoxSize } from "../src/mermaid";
import { nodeCodec, readImage } from "./image-node";
import { nodeWasm } from "./wasm-node";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const env = (): ClientEnv => ({
  codec: nodeCodec(), wasm: nodeWasm, locale: "es",
  fonts: async (kind, style) => kind === "sans" && style === "regular" ? new Uint8Array(readFileSync(path.join(FONTS, "NotoSans-Regular.ttf"))) : null,
});

// Como el que devuelve mermaid.render: width="100%", max-width en el estilo y un <style> propio.
const MERMAID_SVG = '<svg id="m1" width="100%" xmlns="http://www.w3.org/2000/svg" style="max-width: 200px;" viewBox="-8 -8 200 100" role="graphics-document document">'
  + "<style>#m1{font-family:\"Noto Sans\",sans-serif;fill:#333;}</style>"
  + '<g><rect x="0" y="0" width="80" height="40" fill="#ECECFF" stroke="#9370DB"/><text x="10" y="25">Inicio ñ</text></g></svg>';

const file = (svg: string) => ({ name: "diagrama.svg", bytes: new TextEncoder().encode(svg) });

describe("mermaid", () => {
  it("deja el SVG autónomo con tamaño en píxeles y fondo", () => {
    const out = standaloneSvg(MERMAID_SVG, "#FFFFFF");
    expect(out.startsWith("<?xml")).toBe(true);
    expect(out).toContain('<svg width="200" height="100"');
    expect(out).not.toContain("100%");
    expect(out).not.toContain("max-width");
    expect(out).toMatch(/<svg[^>]*><rect x="-8" y="-8" width="200" height="100" fill="#FFFFFF"\/>/);
    expect(viewBoxSize(out)).toEqual({ x: -8, y: -8, width: 200, height: 100 });
    expect(standaloneSvg(MERMAID_SVG, undefined)).not.toContain('fill="#FFFFFF"');
  });

  it("elige el fondo según el tema", () => {
    expect(backgroundOf({ tema: "dark", fondo: "auto" })).toBe("#1f2020");
    expect(backgroundOf({ tema: "dark", fondo: "blanco" })).toBe("#FFFFFF");
    expect(backgroundOf({ tema: "default", fondo: "transparente" })).toBeUndefined();
  });

  it("rechaza un SVG sin viewBox", () => {
    expect(() => viewBoxSize("<svg></svg>")).toThrow();
  });

  it("exporta SVG con el nombre elegido", async () => {
    const res = await runClientTool("mermaid-a-svg", [file(MERMAID_SVG)], { tema: "default", fondo: "auto", nombre: "Mi flujo/../x" }, env());
    expect(res.outputs[0].name).toBe("Mi-flujo-..-x.svg");
    expect(new TextDecoder().decode(res.outputs[0].bytes)).toContain("Inicio ñ");
  });

  it("pinta el PNG a la escala pedida, con el texto", async () => {
    const res = await runClientTool("mermaid-a-png", [file(MERMAID_SVG)], { tema: "default", fondo: "blanco", escala: 3 }, env());
    const img = await readImage(res.outputs[0].bytes);
    expect([img.width, img.height]).toEqual([600, 300]);
    // El texto oscuro (fill #333) está dentro del rectángulo: hay píxeles oscuros en esa zona.
    let dark = 0;
    for (let y = 60; y < 120; y += 1) for (let x = 40; x < 240; x += 1) if (img.data[(y * img.width + x) * 4] < 100) dark += 1;
    expect(dark).toBeGreaterThan(50);
    expect(res.notes).toEqual([]);
  });

  it("limita los megapíxeles y avisa del texto HTML", async () => {
    const huge = MERMAID_SVG.replace('viewBox="-8 -8 200 100"', 'viewBox="0 0 12000 6000"').replace("</svg>", "<foreignObject><div>x</div></foreignObject></svg>");
    const res = await runClientTool("mermaid-a-png", [file(huge)], { tema: "default", fondo: "blanco", escala: 4 }, env());
    const img = await readImage(res.outputs[0].bytes);
    expect(img.width * img.height).toBeLessThanOrEqual(100_000_000);
    expect(res.notes.join(" ")).toMatch(/escala 1\.1[0-9]? .*HTML/s);
  }, 60_000);
});
