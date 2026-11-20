// escribir-pdf (F6-O1, D-234): el documento del editor (JSON de TipTap/ProseMirror) y las opciones de página.

export interface PMMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface PMNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: PMNode[];
  marks?: PMMark[];
  text?: string;
}

export interface PageOptions {
  papel: string;
  orientacion: string;
  margenes_mm: number;
  fuente: "serif" | "sans" | "mono";
  encabezado: string;
  pie: string;
  numeros_pagina: "pie" | "encabezado" | "ninguno";
  formato_numero: "n_de_total" | "n";
  titulo: string;
  autor: string;
  asunto: string;
  palabras_clave: string;
  idioma: "es" | "en";
}

export const PAPER_MM: Record<string, [number, number]> = { A3: [297, 420], A4: [210, 297], A5: [148, 210], Letter: [215.9, 279.4], Legal: [215.9, 355.6] };

export const FONT_NAMES = { serif: "Noto Serif", sans: "Noto Sans", mono: "Noto Sans Mono" } as const;

/** Texto plano de un nodo (para títulos, índice y nombres). */
export function plainText(node: PMNode): string {
  if (node.type === "text") return node.text ?? "";
  if (node.type === "hardBreak") return "\n";
  return (node.content ?? []).map(plainText).join("");
}
