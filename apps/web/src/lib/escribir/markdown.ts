// escribir-pdf (F6-O1, D-234, D-238): exportación a Markdown (GFM) desde el JSON del editor: tablas con barras, listas
// de tareas, fórmulas entre $ y $$, notas al pie [^n] y el índice como lista de enlaces a los títulos (anclas como las
// de GitHub). Comprobado con markdown-it: el código no se escapa, las listas anidadas se sangran según su marcador y lo
// que al principio de una línea sería una lista o una cita se escapa.
import { plainText, type PMMark, type PMNode } from "./model";

const SPECIAL = /([\\`*_[\]#<>$])/g;
const escapeText = (s: string) => s.replace(SPECIAL, "\\$1");
const TICK = "`";

/** Lo que al principio de una línea abriría una lista, una cita o un título se escapa. */
function escapeLineStart(line: string): string {
  return line.replace(/^(\s*)(\d+)([.)])(\s)/, "$1$2\\$3$4").replace(/^(\s*)([-+*])(\s)/, "$1\\$2$3");
}

/** Una valla de comillas invertidas más larga que cualquier racha del contenido. */
function fence(content: string, min: number): string {
  const longest = Math.max(0, ...(content.match(/`+/g) ?? []).map((r) => r.length));
  return TICK.repeat(Math.max(min, longest + 1));
}

function wrapMarks(raw: string, marks: PMMark[] = []): string {
  if (marks.some((m) => m.type === "code")) {
    const f = fence(raw, 1);
    const pad = raw.startsWith(TICK) || raw.endsWith(TICK) ? " " : "";
    return `${f}${pad}${raw}${pad}${f}`;
  }
  // Los espacios de los extremos van fuera de las marcas: «**neg **rita» no es negrita en CommonMark.
  const lead = /^\s*/.exec(raw)?.[0] ?? "";
  const trail = /\s*$/.exec(raw)?.[0] ?? "";
  const core = raw.slice(lead.length, raw.length - trail.length);
  if (!core) return raw;
  let out = escapeText(core);
  if (marks.some((m) => m.type === "bold")) out = `**${out}**`;
  if (marks.some((m) => m.type === "italic")) out = `*${out}*`;
  if (marks.some((m) => m.type === "strike")) out = `~~${out}~~`;
  if (marks.some((m) => m.type === "underline")) out = `<u>${out}</u>`;
  if (marks.some((m) => m.type === "superscript")) out = `<sup>${out}</sup>`;
  if (marks.some((m) => m.type === "subscript")) out = `<sub>${out}</sub>`;
  if (marks.some((m) => m.type === "highlight")) out = `<mark>${out}</mark>`;
  const link = marks.find((m) => m.type === "link")?.attrs?.href;
  if (typeof link === "string" && /^(https?:|mailto:|#)/i.test(link)) out = `[${out}](${link.replace(/[()\s]/g, encodeURIComponent)})`;
  return `${lead}${out}${trail}`;
}

/** Ancla como la de GitHub: minúsculas, sin signos (las letras con tilde se quedan) y espacios a guiones. */
export function slug(text: string): string {
  return text.toLowerCase().trim().replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, "").replace(/\s/g, "-");
}

export function toMarkdown(doc: PMNode, texts: { toc: string; notes: string }): string {
  const notes: string[] = [];
  const headings: { level: number; text: string; anchor: string }[] = [];
  const seen = new Map<string, number>();
  const collect = (n: PMNode) => {
    if (n.type === "heading") {
      const text = plainText(n).trim();
      const base = slug(text);
      const count = seen.get(base) ?? 0;
      seen.set(base, count + 1);
      headings.push({ level: Number(n.attrs?.level ?? 1), text, anchor: count ? `${base}-${count}` : base });
    }
    n.content?.forEach(collect);
  };
  collect(doc);

  const image = (n: PMNode) => `![${String(n.attrs?.alt ?? "").replace(/[[\]]/g, "")}](${String(n.attrs?.src ?? "")})`;

  const inline = (nodes: PMNode[] = []): string => nodes.map((n) => {
    if (n.type === "text") return wrapMarks(n.text ?? "", n.marks);
    if (n.type === "hardBreak") return "  \n";
    if (n.type === "inlineMath") return `$${String(n.attrs?.latex ?? "")}$`;
    if (n.type === "footnote") return `[^${notes.push(String(n.attrs?.text ?? ""))}]`;
    if (n.type === "formField") return n.attrs?.tipo === "casilla" ? "☐" : "\\_".repeat(8);
    if (n.type === "image") return image(n);
    return inline(n.content);
  }).join("");

  const block = (n: PMNode, indent = ""): string => {
    switch (n.type) {
      case "paragraph":
        return indent + escapeLineStart(inline(n.content));
      case "heading":
        return `${"#".repeat(Math.max(1, Math.min(6, Number(n.attrs?.level ?? 1))))} ${inline(n.content)}`;
      case "bulletList":
      case "orderedList":
      case "taskList":
        return (n.content ?? []).map((item, i) => {
          const marker = n.type === "orderedList" ? `${Number(n.attrs?.start ?? 1) + i}.` : n.type === "taskList" ? `- [${item.attrs?.checked ? "x" : " "}]` : "-";
          const [first, ...rest] = item.content ?? [];
          const head = `${indent}${marker} ${first ? block(first).trimStart() : ""}`;
          // Lo anidado se sangra hasta donde empieza el texto del elemento: «1. » son 3 espacios y «10. », 4.
          const child = indent + " ".repeat((n.type === "taskList" ? 2 : marker.length + 1));
          const tail = rest.map((c) => block(c, child)).join("\n");
          return tail ? `${head}\n${tail}` : head;
        }).join("\n");
      case "blockquote":
        return (n.content ?? []).map((c) => block(c)).join("\n\n").split("\n").map((l) => `> ${l}`).join("\n");
      case "codeBlock": {
        const code = plainText(n);
        const f = fence(code, 3);
        return `${f}${String(n.attrs?.language ?? "")}\n${code}\n${f}`;
      }
      case "horizontalRule":
        return "---";
      case "pageBreak":
        return '<div style="page-break-after: always"></div>';
      case "blockMath":
        return `$$\n${String(n.attrs?.latex ?? "")}\n$$`;
      case "image":
        return image(n);
      case "columns":
        return (n.content ?? []).map((c) => block(c)).join("\n\n");
      case "tableOfContents":
        return [`**${texts.toc}**`, "", ...headings.filter((h) => h.level <= 3 && h.text).map((h) => `${"  ".repeat(h.level - 1)}- [${escapeText(h.text)}](#${h.anchor})`)].join("\n");
      case "table": {
        const rows = (n.content ?? []).map((row) => (row.content ?? []).map((cell) => (cell.content ?? []).map((c) => block(c)).join(" ").replace(/\|/g, "\\|").replace(/\n+/g, " ")));
        if (!rows.length) return "";
        const width = Math.max(...rows.map((r) => r.length));
        const pad = (r: string[]) => `| ${Array.from({ length: width }, (_, i) => r[i] ?? "").join(" | ")} |`;
        return [pad(rows[0]), `| ${Array.from({ length: width }, () => "---").join(" | ")} |`, ...rows.slice(1).map(pad)].join("\n");
      }
      default:
        return (n.content ?? []).map((c) => block(c, indent)).join("\n\n");
    }
  };

  const body = (doc.content ?? []).map((n) => block(n)).filter((s) => s !== "").join("\n\n");
  const footer = notes.length ? `\n\n${notes.map((t, i) => `[^${i + 1}]: ${t.replace(/\n/g, " ")}`).join("\n")}` : "";
  return `${body}${footer}\n`;
}
