// comparar-pdf (A.7): diferencias palabra a palabra con diff-match-patch. Sin pdf-lib: la usa también la web.
import DiffMatchPatch from "diff-match-patch";

import type { TextChar } from "./pdfium";
import { boxesToAreas, foldChar, type Area, type PageText } from "./textsearch";


export interface WordToken {
  text: string;
  norm: string;
  page: number;
  chars: TextChar[];
}

export interface CompareOptions {
  ignorar_mayusculas_espacios: boolean;
}

export interface Change {
  kind: "added" | "removed" | "changed";
  a: { page: number; text: string; areas: Area[] } | null;
  b: { page: number; text: string; areas: Area[] } | null;
}

/** Palabras con su página y las cajas de sus caracteres. */
export function tokenize(pages: PageText[], o: CompareOptions): WordToken[] {
  const tokens: WordToken[] = [];
  for (const { page, chars } of pages) {
    let cur: TextChar[] = [];
    const flush = () => {
      if (!cur.length) return;
      const t = cur.map((c) => c.ch).join("");
      tokens.push({ text: t, norm: o.ignorar_mayusculas_espacios ? Array.from(t).map(foldChar).join("") : t, page, chars: cur });
      cur = [];
    };
    for (const c of chars) {
      if (!c.ch || /\s/.test(c.ch)) flush();
      else cur.push(c);
    }
    flush();
  }
  return tokens;
}

function span(tokens: WordToken[]): { page: number; text: string; areas: Area[] } | null {
  if (!tokens.length) return null;
  const page = tokens[0].page;
  const same = tokens.filter((t) => t.page === page);
  return { page, text: tokens.map((t) => t.text).join(" "), areas: boxesToAreas(page, same.flatMap((t) => t.chars)) };
}

/** Diferencias palabra a palabra con diff-match-patch: añadido, borrado y cambiado, con sus zonas en A y en B. */
export function compareTexts(a: PageText[], b: PageText[], o: CompareOptions): Change[] {
  const ta = tokenize(a, o);
  const tb = tokenize(b, o);
  // Cada palabra distinta se codifica como un carácter del plano básico (como diff_linesToChars).
  const codes = new Map<string, string>();
  let next = 0x100;
  const encode = (tokens: WordToken[]) => tokens.map((t) => {
    let c = codes.get(t.norm);
    if (!c) {
      if (next === 0xd800) next = 0xe000;
      c = next <= 0xfffd ? String.fromCharCode(next++) : "�";
      codes.set(t.norm, c);
    }
    return c;
  }).join("");
  const dmp = new DiffMatchPatch();
  dmp.Diff_Timeout = 5;
  // Cada carácter es ya una palabra: sin limpieza semántica, que juntaría cambios separados por palabras cortas.
  const diffs = dmp.diff_main(encode(ta), encode(tb), false);
  const changes: Change[] = [];
  // Un cambio no cruza páginas: lo que cae en páginas anteriores se separa como añadido o borrado.
  const byPage = (tokens: WordToken[]) => tokens.reduce<WordToken[][]>((groups, t) => {
    const last = groups[groups.length - 1];
    if (last && last[0].page === t.page) last.push(t);
    else groups.push([t]);
    return groups;
  }, []);
  const emit = (removed: WordToken[], added: WordToken[]) => {
    const rg = byPage(removed);
    const ag = byPage(added);
    while (rg.length > (ag.length ? 1 : 0)) changes.push({ kind: "removed", a: span(rg.shift()!), b: null });
    while (ag.length > (rg.length ? 1 : 0)) changes.push({ kind: "added", a: null, b: span(ag.shift()!) });
    if (rg.length && ag.length) changes.push({ kind: "changed", a: span(rg[0]), b: span(ag[0]) });
  };
  let ia = 0;
  let ib = 0;
  for (let k = 0; k < diffs.length; k += 1) {
    const [op, data] = diffs[k];
    if (op === 0) {
      ia += data.length;
      ib += data.length;
    } else if (op === -1) {
      const removed = ta.slice(ia, ia + data.length);
      ia += data.length;
      let added: WordToken[] = [];
      if (diffs[k + 1]?.[0] === 1) {
        added = tb.slice(ib, ib + diffs[k + 1][1].length);
        ib += diffs[k + 1][1].length;
        k += 1;
      }
      emit(removed, added);
    } else {
      const added = tb.slice(ib, ib + data.length);
      ib += data.length;
      emit([], added);
    }
  }
  return changes;
}
