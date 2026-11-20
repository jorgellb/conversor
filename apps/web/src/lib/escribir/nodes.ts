// escribir-pdf (A.1, F6-O1, D-234): nodos propios del editor TipTap (MIT) que no trae el paquete: salto de página,
// columnas, nota al pie, campo rellenable e índice. Su HTML es el que lee la exportación (html.ts).
import { Node, mergeAttributes } from "@tiptap/core";
import Image from "@tiptap/extension-image";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    escribir: {
      insertPageBreak: () => ReturnType;
      insertColumns: (count: 2 | 3) => ReturnType;
      insertFootnote: (text: string) => ReturnType;
      insertField: (attrs: { tipo: "texto" | "casilla" | "fecha"; nombre: string; ancho: number }) => ReturnType;
      insertToc: () => ReturnType;
    };
  }
}

export const PageBreak = Node.create({
  name: "pageBreak",
  group: "block",
  atom: true,
  selectable: true,
  parseHTML: () => [{ tag: "hr.salto-pagina" }, { tag: 'div[data-type="page-break"]' }],
  renderHTML: ({ HTMLAttributes }) => ["hr", mergeAttributes(HTMLAttributes, { class: "salto-pagina", "data-type": "page-break" })],
  addCommands() {
    // Con un párrafo detrás: si no, el nodo queda seleccionado y lo siguiente que se escribe lo sustituye.
    return { insertPageBreak: () => ({ commands }) => commands.insertContent([{ type: this.name }, { type: "paragraph" }]) };
  },
  addKeyboardShortcuts() {
    return { "Mod-Enter": () => this.editor.commands.insertPageBreak() };
  },
});

export const Columns = Node.create({
  name: "columns",
  group: "block",
  content: "block+",
  defining: true,
  addAttributes() {
    return {
      count: {
        default: 2,
        parseHTML: (el) => Math.max(2, Math.min(3, Number(el.getAttribute("data-columnas")) || 2)),
        renderHTML: (attrs) => ({ "data-columnas": String(attrs.count) }),
      },
    };
  },
  parseHTML: () => [{ tag: "div.columnas" }],
  renderHTML: ({ HTMLAttributes }) => ["div", mergeAttributes(HTMLAttributes, { class: "columnas" }), 0],
  addCommands() {
    return {
      insertColumns: (count) => ({ commands }) => commands.insertContent({ type: this.name, attrs: { count }, content: [{ type: "paragraph" }] }),
    };
  },
});

/** Nota al pie: un número volado en el texto (contador CSS) y el texto de la nota, que se exporta al final del documento. */
export const Footnote = Node.create({
  name: "footnote",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return { text: { default: "", parseHTML: (el) => el.getAttribute("data-nota") ?? "", renderHTML: (attrs) => ({ "data-nota": String(attrs.text ?? "") }) } };
  },
  parseHTML: () => [{ tag: "sup.nota" }],
  renderHTML: ({ HTMLAttributes, node }) => ["sup", mergeAttributes(HTMLAttributes, { class: "nota", title: String(node.attrs.text ?? "") })],
  addCommands() {
    return { insertFootnote: (text) => ({ commands }) => commands.insertContent({ type: this.name, attrs: { text } }) };
  },
});

/** Campo rellenable: en el PDF, un enlace https://campo.invalid/<tipo>/<nombre> que la exportación convierte en campo. */
export const FormField = Node.create({
  name: "formField",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return {
      tipo: { default: "texto", parseHTML: (el) => el.getAttribute("data-tipo") ?? "texto", renderHTML: (a) => ({ "data-tipo": a.tipo }) },
      nombre: { default: "campo", parseHTML: (el) => el.getAttribute("data-nombre") ?? "campo", renderHTML: (a) => ({ "data-nombre": a.nombre }) },
      ancho: {
        default: 50,
        parseHTML: (el) => Math.max(5, Math.min(180, Number(el.getAttribute("data-ancho")) || 50)),
        renderHTML: (a) => ({ "data-ancho": String(a.ancho), style: `width:${a.tipo === "casilla" ? 4 : a.ancho}mm` }),
      },
    };
  },
  parseHTML: () => [{ tag: "span.campo-editor" }],
  renderHTML: ({ HTMLAttributes, node }) => ["span", mergeAttributes(HTMLAttributes, { class: "campo-editor", title: String(node.attrs.nombre) }), String(node.attrs.nombre)],
  addCommands() {
    return { insertField: (attrs) => ({ commands }) => commands.insertContent({ type: this.name, attrs }) };
  },
});

/** Índice automático: en el editor, la lista de títulos; en el PDF, con los números de página de la segunda pasada. */
export const TableOfContents = Node.create({
  name: "tableOfContents",
  group: "block",
  atom: true,
  selectable: true,
  parseHTML: () => [{ tag: 'nav[data-type="indice"]' }],
  renderHTML: ({ HTMLAttributes }) => ["nav", mergeAttributes(HTMLAttributes, { "data-type": "indice", class: "indice-editor" })],
  addCommands() {
    return { insertToc: () => ({ commands }) => commands.insertContent([{ type: this.name }, { type: "paragraph" }]) };
  },
});

/** Imagen con su ancho en porcentaje de la columna. */
export const SizedImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: 100,
        parseHTML: (el) => Math.max(10, Math.min(100, Number((el.getAttribute("data-ancho") ?? "").replace("%", "")) || 100)),
        renderHTML: (a) => ({ "data-ancho": String(a.width), style: `width:${a.width}%` }),
      },
    };
  },
});
