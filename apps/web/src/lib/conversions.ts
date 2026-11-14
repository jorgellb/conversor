// convertir-archivo (7.22): qué salidas tiene cada tipo real, sacado del registro. Para cada par (entrada, salida) gana
// la herramienta más concreta (jpg-a-png antes que convertir-imagen), y a igualdad la del navegador. Las combinaciones
// que no tienen herramienta propia (bmp a ICO, por ejemplo) se hacen con la genérica y su formato fijado.
import type { ToolSpec } from "./registry";

export interface Route {
  from: string;
  /** Extensión de salida; «pdfa» (PDF/A) y «base64» son salidas con nombre propio. */
  to: string;
  tool: string;
  where: ToolSpec["where"];
  /** Opciones fijadas de la herramienta para esta salida (las genéricas eligen el formato con una opción). */
  preset: Record<string, string>;
}

/** Herramientas genéricas cuya opción elige la salida. */
const FORMAT_OPTION: Record<string, string> = {
  "convertir-imagen": "formato",
  "convertir-desde-pdf": "formato",
  "transcribir-audio": "formato",
  "video-a-subtitulos": "formato",
  "imagen-a-texto": "salida",
  "imagen-a-excel": "formato",
};
/** Menos concretas: solo se usan si no hay otra. */
const GENERIC = new Set(["convertir-imagen", "convertir-desde-pdf", "convertir-a-pdf", "imagenes-a-pdf"]);
/** Conversores que no se llaman «x-a-y». */
const NAMED = new Set(["convertir-imagen", "convertir-desde-pdf", "convertir-a-pdf", "transcribir-audio"]);
/** Sin archivo de entrada (web-a-pdf), con salida solo en ZIP (pdf-a-imagenes, cubierta por pdf-a-jpg y demás) o que
 * solo sirven para un tipo de imagen concreto (ticket-a-excel: tickets de compra, no cualquier imagen a Excel). */
const NOT_CONVERTERS = new Set(["web-a-pdf", "pdf-a-imagenes", "ticket-a-excel"]);
/** Valores de formato que no son una salida («todos» los formatos, «ambos»). */
const SEVERAL = new Set(["todos", "ambos"]);
const WHERE_RANK: Record<ToolSpec["where"], number> = { client: 0, hybrid: 1, server: 2 };

export function isConverter(tool: ToolSpec): boolean {
  if (NOT_CONVERTERS.has(tool.slug_es) || tool.canonical_of || !tool.inputs.length) return false;
  return tool.slug_es.includes("-a-") || NAMED.has(tool.slug_es);
}

/** Salidas de una herramienta con lo que hay que fijar para cada una. */
export function targets(tool: ToolSpec): { to: string; preset: Record<string, string> }[] {
  const option = FORMAT_OPTION[tool.slug_es];
  const values = option ? tool.options_schema.properties[option]?.enum : undefined;
  if (option && values) return values.map(String).filter((v) => !SEVERAL.has(v)).map((v) => ({ to: v, preset: { [option]: v } }));
  if (tool.slug_es === "pdf-a-pdfa") return [{ to: "pdfa", preset: {} }];
  if (tool.slug_es === "imagen-a-base64") return [{ to: "base64", preset: {} }];
  return tool.outputs.filter((o) => o !== "zip").map((to) => ({ to, preset: {} }));
}

/** Orden de preferencia: concreta antes que genérica, la que se llama como la entrada (ogg-a-mp3 para un OGG, aunque
 * opus-a-mp3 también lo admita), la del navegador, y la que admite menos entradas y da menos salidas. */
function rank(tool: ToolSpec, from: string, count: number): number[] {
  return [GENERIC.has(tool.slug_es) ? 1 : 0, tool.slug_es.startsWith(`${from}-a-`) ? 0 : 1, WHERE_RANK[tool.where], tool.inputs.length, count];
}

const before = (a: number[], b: number[]) => {
  for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return a[i] < b[i];
  return false;
};

/** Rutas de conversión por tipo de entrada, sin las herramientas apagadas en este despliegue. */
export function buildRoutes(tools: ToolSpec[], disabled: Set<string> = new Set()): Record<string, Route[]> {
  const best = new Map<string, { route: Route; rank: number[] }>();
  for (const tool of tools) {
    if (!isConverter(tool) || disabled.has(tool.slug_es)) continue;
    const outs = targets(tool);
    for (const from of tool.inputs) {
      for (const { to, preset } of outs) {
        if (to === from) continue;
        const key = `${from}>${to}`;
        const r = rank(tool, from, outs.length);
        const current = best.get(key);
        if (!current || before(r, current.rank)) best.set(key, { route: { from, to, tool: tool.slug_es, where: tool.where, preset }, rank: r });
      }
    }
  }
  const routes: Record<string, Route[]> = {};
  for (const { route } of best.values()) (routes[route.from] ??= []).push(route);
  for (const list of Object.values(routes)) list.sort((a, b) => ORDER.indexOf(a.to) - ORDER.indexOf(b.to));
  return routes;
}

/** El tipo con el que se busca la ruta: dentro de los contenedores ambiguos manda la extensión, como en el servidor. */
export function routeKind(detected: string, declared: string): string {
  if (detected === "iwork" && ["pages", "key", "numbers"].includes(declared)) return declared;
  if (detected === "zip" && (declared === "cbz" || declared === "cbr")) return declared;
  if (detected === "rar" && declared === "cbr") return "cbr";
  if (detected === "mobi" && ["azw3", "azw"].includes(declared)) return "azw3";
  if (detected === "mp4" && declared === "m4a") return "m4a";
  return detected;
}

export type Group = "document" | "image" | "audio" | "subtitles" | "other";

export const GROUPS: Record<Group, string[]> = {
  document: ["pdf", "pdfa", "docx", "odt", "rtf", "txt", "md", "html", "epub", "xlsx", "ods", "csv", "json", "pptx", "odp"],
  image: ["jpg", "png", "webp", "avif", "gif", "bmp", "tiff", "ico", "svg"],
  audio: ["mp3", "wav"],
  subtitles: ["srt", "vtt"],
  other: ["base64"],
};

const ORDER = Object.values(GROUPS).flat();

export function groupOf(to: string): Group {
  return (Object.keys(GROUPS) as Group[]).find((g) => GROUPS[g].includes(to)) ?? "other";
}

const NAMES: Record<string, string> = {
  pdfa: "PDF/A", docx: "Word (DOCX)", xlsx: "Excel (XLSX)", pptx: "PowerPoint (PPTX)", odt: "ODT", ods: "ODS", odp: "ODP",
  md: "Markdown", base64: "Base64",
};

/** Nombre visible de un formato («Word (DOCX)», «PNG»). */
export function formatName(ext: string): string {
  return NAMES[ext] ?? ext.toUpperCase();
}
