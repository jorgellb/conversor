// Regresión visual de 16.1: genera con el código del navegador los PDF de folleto-pdf, varias-paginas-por-hoja,
// numerar-paginas-pdf y marca-de-agua-pdf a partir de una muestra fija. Con VISUAL_PDF_DIR los escribe en esa carpeta y
// tests/test_regresion_visual.py los pasa a PNG con pypdfium2 y los compara con las referencias de tests/visual/pdf/.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { PDFDocument, StandardFonts, rgb } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { runClientTool, type ClientEnv } from "../src/index";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const FONT_FILES = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
} as const;

// Las mismas fuentes que carga el worker del navegador desde /fonts (client-tool.worker.ts).
const env: ClientEnv = {
  fonts: async (kind, style = "regular") => new Uint8Array(readFileSync(path.join(FONTS, `${FONT_FILES[kind][style]}.ttf`))),
};

const COLORS = [rgb(0.85, 0.2, 0.2), rgb(0.2, 0.55, 0.25), rgb(0.2, 0.35, 0.8), rgb(0.85, 0.6, 0.1)];

/** Muestra fija: páginas A5 verticales con marco, número grande y un bloque de color en una esquina distinta. */
async function sample(pages: number): Promise<{ name: string; bytes: Uint8Array }> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.HelveticaBold);
  for (let i = 0; i < pages; i += 1) {
    const page = doc.addPage([420, 595]);
    page.drawRectangle({ x: 12, y: 12, width: 396, height: 571, borderColor: rgb(0.1, 0.1, 0.1), borderWidth: 3 });
    const corner = i % 4;
    page.drawRectangle({ x: corner % 2 === 0 ? 24 : 316, y: corner < 2 ? 491 : 24, width: 80, height: 80, color: COLORS[i % COLORS.length] });
    const label = String(i + 1);
    page.drawText(label, { x: 210 - font.widthOfTextAtSize(label, 160) / 2, y: 240, size: 160, font, color: rgb(0.15, 0.15, 0.15) });
  }
  return { name: "muestra.pdf", bytes: await doc.save({ useObjectStreams: false }) };
}

// Opciones por defecto del registro (Anexo A), salvo lo que hace visible el resultado en la captura.
const CASES = {
  "folleto-pdf": {
    pages: 8,
    options: { papel: "a4_a5", encuadernacion: "izquierda", medianil: 0, hojas_por_cuadernillo: 0, contraportada_al_final: true, salida: "pdf" },
  },
  "varias-paginas-por-hoja": {
    pages: 6,
    options: { por_hoja: 4, orden: "horizontal", hoja: "A4", orientacion: "auto", margenes: 5, direccion: "ltr", bordes: true, color_borde: "#000000", ancho_borde: 0.5 },
  },
  "numerar-paginas-pdf": {
    pages: 3,
    options: {
      patron: "Página {NUM} de {CNT}", posicion: "abajo-centro", fuente: "sans", tamano: 14, color: "#000000", opacidad: 1, angulo: 0,
      margen_x: 5, margen_y: 5, primera_pagina: 1, primer_numero: 1, ultima_pagina: null, total_fijo: null, espejo: false, estilo: "arabigo",
    },
  },
  "marca-de-agua-pdf": {
    pages: 2,
    options: {
      tipo: "texto", texto: "CONFIDENCIAL", escala_imagen: 50, fuente: "sans", tamano: 40, color: "#E67610", opacidad: 0.4, angulo: -45,
      posicion: "centro", espacio_x: 5, espacio_y: 5, paginas: "todas", capa: "encima", aplanar: false,
    },
  },
} as const;

const EXPECTED_PAGES: Record<keyof typeof CASES, number> = {
  "folleto-pdf": 4, // 8 páginas A5 → 2 hojas A4 a doble cara = 4 caras
  "varias-paginas-por-hoja": 2,
  "numerar-paginas-pdf": 3,
  "marca-de-agua-pdf": 2,
};

describe("PDF de la regresión visual (16.1)", () => {
  for (const [slug, { pages, options }] of Object.entries(CASES) as [keyof typeof CASES, (typeof CASES)[keyof typeof CASES]][]) {
    it(`${slug} con la muestra fija`, async () => {
      const res = await runClientTool(slug, [await sample(pages)], options, env);
      const pdf = res.outputs.find((o) => o.name.endsWith(".pdf"))!;
      expect((await PDFDocument.load(pdf.bytes)).getPageCount()).toBe(EXPECTED_PAGES[slug]);
      const out = process.env.VISUAL_PDF_DIR;
      if (out) {
        mkdirSync(out, { recursive: true });
        writeFileSync(path.join(out, `${slug}.pdf`), pdf.bytes);
      }
    });
  }
});
