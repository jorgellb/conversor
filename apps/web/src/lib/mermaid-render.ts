// mermaid-a-svg y mermaid-a-png (7.13, F6-N, D-231): Mermaid dibuja el diagrama en la página, porque mide el texto con el
// DOM. «strict» sanea las etiquetas (DOMPurify) y quita los clics; las etiquetas van como texto SVG (sin HTML) para que
// resvg las pinte igual en el PNG; y el texto se mide con la misma Noto Sans que usa resvg, cargada desde /fonts.
import type { Mermaid } from "mermaid";

export const MAX_CODE = 100_000;
let mermaidPromise: Promise<Mermaid> | null = null;
let fontsPromise: Promise<void> | null = null;
let counter = 0;

const FONT_FAMILY = '"Noto Sans", sans-serif';

function loadFonts(): Promise<void> {
  fontsPromise ??= (async () => {
    if (typeof FontFace === "undefined") return;
    const faces = [
      new FontFace("Noto Sans", "url(/fonts/NotoSans-Regular.ttf)", { weight: "400" }),
      new FontFace("Noto Sans", "url(/fonts/NotoSans-Bold.ttf)", { weight: "700" }),
      new FontFace("Noto Sans", "url(/fonts/NotoSans-Italic.ttf)", { weight: "400", style: "italic" }),
    ];
    await Promise.all(faces.map(async (face) => {
      try {
        document.fonts.add(await face.load());
      } catch {
        // Sin la fuente se mide con la del sistema; el PNG puede salir algo más justo.
      }
    }));
  })();
  return fontsPromise;
}

function loadMermaid(): Promise<Mermaid> {
  mermaidPromise ??= import("mermaid").then((m) => m.default);
  mermaidPromise.catch(() => {
    mermaidPromise = null;
  });
  return mermaidPromise;
}

export class MermaidSyntaxError extends Error {
  line: number | null;
  constructor(message: string, line: number | null) {
    super(message);
    this.line = line;
  }
}

/** El primer bloque ```mermaid de un Markdown o, si no hay, el texto entero. */
export function codeFromFile(text: string): string {
  const fence = /^(`{3,}|~{3,})\s*mermaid\b[^\n]*\n([\s\S]*?)^\1\s*$/m.exec(text);
  return (fence ? fence[2] : text).replace(/^﻿/, "").replace(/\r\n?/g, "\n").trimEnd();
}

function lineOf(err: unknown): number | null {
  const hash = (err as { hash?: { line?: number; loc?: { first_line?: number } } })?.hash;
  if (hash?.loc?.first_line) return hash.loc.first_line;
  if (typeof hash?.line === "number") return hash.line + 1;
  const m = /line (\d+)/i.exec(String((err as Error)?.message ?? err));
  return m ? Number(m[1]) : null;
}

/** El SVG del diagrama con el tema elegido. Lanza MermaidSyntaxError si el código no es válido. */
export async function renderMermaid(code: string, theme: string): Promise<string> {
  if (!code.trim()) throw new MermaidSyntaxError("empty", null);
  if (code.length > MAX_CODE) throw new MermaidSyntaxError("too_long", null);
  const [mermaid] = await Promise.all([loadMermaid(), loadFonts()]);
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: theme as "default",
    fontFamily: FONT_FAMILY,
    themeVariables: { fontFamily: FONT_FAMILY },
    htmlLabels: false,
    flowchart: { htmlLabels: false },
    // La disposición ELK (elkjs, EPL-2.0) no se incluye en la web (D-231): siempre dagre.
    layout: "dagre",
    maxTextSize: MAX_CODE,
    maxEdges: 2000,
    suppressErrorRendering: true,
  });
  try {
    await mermaid.parse(code);
  } catch (err) {
    throw new MermaidSyntaxError(String((err as Error)?.message ?? err).split("\n").slice(0, 4).join("\n"), lineOf(err));
  }
  counter += 1;
  const id = `mermaid-diagrama-${counter}`;
  try {
    const { svg } = await mermaid.render(id, code);
    return svg;
  } catch (err) {
    throw new MermaidSyntaxError(String((err as Error)?.message ?? err).split("\n").slice(0, 4).join("\n"), lineOf(err));
  } finally {
    document.getElementById(id)?.remove();
    document.getElementById(`d${id}`)?.remove();
  }
}
