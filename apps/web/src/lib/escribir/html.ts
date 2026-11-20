// escribir-pdf (F6-O1, D-234): del HTML del editor al cuerpo que se envía al servidor para el PDF. Se hace en la página
// con el DOM: ids de los títulos, índice con sus enlaces (el servidor pone los números en la segunda pasada), fórmulas
// en MathML (Chromium las pinta sin red ni fuentes de KaTeX), notas al pie numeradas al final, campos como enlaces
// https://campo.invalid/… (pdf-lib los cambia por campos) y solo imágenes en data: (Gotenberg no tiene red).
import katex from "katex";

export interface ExportTexts {
  toc: string;
  notes: string;
}

export const FIELD_HOST = "campo.invalid";

function mathml(latex: string, display: boolean): string {
  return katex.renderToString(latex, { output: "mathml", displayMode: display, throwOnError: false, strict: "ignore", trust: false, maxSize: 50, maxExpand: 500 });
}

export function exportHtml(editorHtml: string, t: ExportTexts): string {
  const doc = new DOMParser().parseFromString(`<!doctype html><html><body>${editorHtml}</body></html>`, "text/html");
  const body = doc.body;
  // Limpieza de lo más evidente (scripts, manejadores, marcos, formularios y recursos de fuera). El límite de confianza es
  // el servidor: la página que imprime Chromium lleva una CSP que no carga nada que no esté en data: (D-238).
  [...body.querySelectorAll("script,style,iframe,frame,object,embed,link,meta,base,form,input,button,select,textarea,video,audio,source,picture")].forEach((el) => el.remove());
  [...body.querySelectorAll("*")].forEach((el) => {
    for (const attr of [...el.attributes]) {
      if (/^on/i.test(attr.name) || attr.name === "contenteditable" || attr.name === "draggable") el.removeAttribute(attr.name);
      if ((attr.name === "href" || attr.name === "src" || attr.name === "xlink:href") && /^\s*(javascript|vbscript|data:text)/i.test(attr.value)) el.removeAttribute(attr.name);
      if (["srcset", "poster", "background", "srcdoc", "formaction"].includes(attr.name)) el.removeAttribute(attr.name);
      if (attr.name === "style" && /url\(/i.test(attr.value)) el.removeAttribute(attr.name);
    }
  });
  [...body.querySelectorAll("img")].forEach((img) => {
    if (!(img.getAttribute("src") ?? "").startsWith("data:image/")) img.remove();
  });

  const headings = [...body.querySelectorAll("h1,h2,h3,h4,h5,h6")] as HTMLElement[];
  headings.forEach((h, i) => {
    h.id = `h-${i + 1}`;
  });

  [...body.querySelectorAll('nav[data-type="indice"]')].forEach((nav) => {
    const out = doc.createElement("nav");
    out.className = "indice";
    const title = doc.createElement("h2");
    title.textContent = t.toc;
    title.setAttribute("data-indice-titulo", "");
    const list = doc.createElement("ol");
    for (const h of headings) {
      const level = Number(h.tagName[1]);
      if (level > 3 || !h.textContent?.trim()) continue;
      const li = doc.createElement("li");
      li.setAttribute("data-nivel", String(level));
      const a = doc.createElement("a");
      a.setAttribute("href", `#${h.id}`);
      a.textContent = h.textContent.trim();
      const dots = doc.createElement("span");
      dots.className = "toc-dots";
      const page = doc.createElement("span");
      page.className = "toc-page";
      page.setAttribute("data-toc", h.id);
      li.append(a, dots, page);
      list.append(li);
    }
    out.append(title, list);
    nav.replaceWith(out);
  });

  [...body.querySelectorAll('[data-type="inline-math"],[data-type="block-math"]')].forEach((el) => {
    const display = el.getAttribute("data-type") === "block-math";
    const wrap = doc.createElement(display ? "div" : "span");
    wrap.className = display ? "formula" : "formula-en-linea";
    wrap.innerHTML = mathml(el.getAttribute("data-latex") ?? "", display);
    el.replaceWith(wrap);
  });

  const notes: string[] = [];
  [...body.querySelectorAll("sup.nota")].forEach((sup) => {
    const n = notes.push(sup.getAttribute("data-nota") ?? "");
    const a = doc.createElement("a");
    a.setAttribute("href", `#nota-${n}`);
    a.id = `ref-nota-${n}`;
    a.textContent = String(n);
    sup.replaceChildren(a);
    sup.removeAttribute("data-nota");
    sup.removeAttribute("title");
  });
  if (notes.length) {
    const section = doc.createElement("section");
    section.className = "notas";
    const h = doc.createElement("h2");
    h.textContent = t.notes;
    const ol = doc.createElement("ol");
    notes.forEach((text, i) => {
      const li = doc.createElement("li");
      li.id = `nota-${i + 1}`;
      li.textContent = text;
      ol.append(li);
    });
    section.append(h, ol);
    body.append(section);
  }

  const used = new Map<string, number>();
  [...body.querySelectorAll("span.campo-editor")].forEach((span) => {
    const tipo = ["texto", "casilla", "fecha"].includes(span.getAttribute("data-tipo") ?? "") ? span.getAttribute("data-tipo")! : "texto";
    // Sin puntos: en un PDF separan los niveles del nombre del campo (D-238).
    let name = (span.getAttribute("data-nombre") ?? "campo").replace(/\./g, "·").trim().slice(0, 60) || "campo";
    // Nombres únicos: dos campos con el mismo nombre en un PDF comparten valor.
    const count = (used.get(name) ?? 0) + 1;
    used.set(name, count);
    if (count > 1) name = `${name} ${count}`;
    const width = Math.max(5, Math.min(180, Number(span.getAttribute("data-ancho")) || 50));
    const a = doc.createElement("a");
    a.className = "campo";
    a.setAttribute("data-tipo", tipo);
    a.setAttribute("href", `https://${FIELD_HOST}/${tipo}/${encodeURIComponent(name)}`);
    a.style.width = tipo === "casilla" ? "4mm" : `${width}mm`;
    a.innerHTML = "&nbsp;";
    span.replaceWith(a);
  });
  return body.innerHTML;
}
