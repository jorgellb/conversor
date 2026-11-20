// escribir-pdf (F6-O1, D-234): exportación a Markdown (GFM) desde el JSON del editor: tablas con barras, listas de
// tareas, fórmulas entre $ y $$, notas al pie [^n] y el índice como lista de enlaces a los títulos.
import { plainText, type PMMark, type PMNode } from "./model";

// «|» solo se escapa dentro de las tablas.
const SPECIAL = /([\\`*_[\]#<>])/g;
const escapeText = (s: string) => s.replace(SPECIAL, "\\$1");
const FENCE = "```";
const TICK = "`";

function wrapMarks(text: string, marks: PMMark[] = []): string {
  if (marks.some((m) => m.type === "code")) return TICK + text.split(TICK).join("\\" + TICK) + TICK;
  let out = text;
  if (marks.some((m) => m.type === "bold")) out = `**${out}**`;
  if (marks.some((m) => m.type === "italic")) out = `*${out}*`;
  if (marks.some((m) => m.type === "strike")) out = `~~${out}~~`;
  if (marks.some((m) => m.type === "underline")) out = `<u>${out}</u>`;
  if (marks.some((m) => m.type === "superscript")) out = `<sup>${out}</sup>`;
  if (marks.some((m) => m.type === "subscript")) out = `<sub>${out}</sub>`;
  if (marks.some((m) => m.type === "highlight")) out = `<mark>${out}</mark>`;
  const link = marks.find((m) => m.type === "link")?.attrs?.href;
  if (typeof link === "string" && /^(https?:|mailto:|#)/i.test(link)) out = `[${out}](${link.replace(/[()\s]/g, encodeURIComponent)})`;
  return out;
}

export function slug(text: string): string {
  return text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
}

export function toMarkdown(doc: PMNode, texts: { toc: string; notes: string }): string {
  const notes: string[] = [];
  const headings: { level: number; text: string }[] = [];
  const collect = (n: PMNode) => {
    if (n.type === "heading") headings.push({ level: Number(n.attrs?.level ?? 1), text: plainText(n).trim() });
    n.content?.forEach(collect);
  };
  collect(doc);

  const image = (n: PMNode) => `![${String(n.attrs?.alt ?? "").replace(/[[\]]/g, "")}](${String(n.attrs?.src ?? "")})`;

  const inline = (nodes: PMNode[] = []): string => nodes.map((n) => {
    if (n.type === "text") return wrapMarks(escapeText(n.text ?? ""), n.marks);
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
        return indent + inline(n.content);
      case "heading":
        return `${"#".repeat(Math.max(1, Math.min(6, Number(n.attrs?.level ?? 1))))} ${inline(n.content)}`;
      case "bulletList":
      case "orderedList":
      case "taskList":
        return (n.content ?? []).map((item, i) => {
          const marker = n.type === "orderedList" ? `${Number(n.attrs?.start ?? 1) + i}.` : n.type === "taskList" ? `- [${item.attrs?.checked ? "x" : " "}]` : "-";
          const [first, ...rest] = item.content ?? [];
          const head = `${indent}${marker} ${first ? block(first).trimStart() : ""}`;
          const tail = rest.map((c) => block(c, `${indent}  `)).join("\n");
          return tail ? `${head}\n${tail}` : head;
        }).join("\n");
      case "blockquote":
        return (n.content ?? []).map((c) => block(c)).join("\n\n").split("\n").map((l) => `> ${l}`).join("\n");
      case "codeBlock":
        return `${FENCE}${String(n.attrs?.language ?? "")}\n${plainText(n)}\n${FENCE}`;
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
        return [`**${texts.toc}**`, "", ...headings.filter((h) => h.level <= 3 && h.text).map((h) => `${"  ".repeat(h.level - 1)}- [${escapeText(h.text)}](#${slug(h.text)})`)].join("\n");
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
