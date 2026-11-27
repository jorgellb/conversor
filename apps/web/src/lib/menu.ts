// Secciones de cada categoría (D-272): el submenú de la cabecera y los bloques del apartado de la categoría. Cada
// herramienta activa va en una sola sección de su categoría (lo comprueba test/menu.test.ts) y el orden de cada lista es
// el del submenú: las más buscadas primero.
import type { Locale } from "@/i18n/routing";

import { disabledByEnv } from "./flags";
import { nameOf, summaryOf, TOOLS } from "./registry";
import { toolPath } from "./site";

export type MenuGroupSpec = { id: string; es: string; en: string; tools: string[] };

export const MENU_GROUPS: Record<string, MenuGroupSpec[]> = {
  pdf: [
    { id: "desde-pdf", es: "Convertir desde PDF", en: "Convert from PDF", tools: [
      "pdf-a-word", "pdf-a-excel", "pdf-a-ppt", "pdf-a-jpg", "pdf-a-png", "pdf-a-txt", "pdf-a-markdown", "pdf-a-html", "pdf-a-epub",
      "pdf-a-odt", "pdf-a-rtf", "pdf-a-ods", "pdf-a-odp", "pdf-a-csv", "pdf-a-json", "pdf-a-webp", "pdf-a-imagenes", "pdf-a-tiff",
      "pdf-a-svg", "extraer-imagenes-pdf", "convertir-desde-pdf"] },
    { id: "a-pdf", es: "Convertir a PDF", en: "Convert to PDF", tools: [
      "jpg-a-pdf", "imagenes-a-pdf", "png-a-pdf", "escaner-pdf", "heic-a-pdf", "webp-a-pdf", "gif-a-pdf", "bmp-a-pdf", "tiff-a-pdf",
      "cbz-a-pdf", "cbr-a-pdf", "djvu-a-pdf", "eml-a-pdf", "msg-a-pdf", "dxf-a-pdf"] },
    { id: "organizar", es: "Organizar páginas", en: "Organise pages", tools: [
      "unir-pdf", "dividir-pdf", "organizar-pdf", "girar-pdf", "eliminar-paginas-pdf", "extraer-paginas-pdf", "numerar-paginas-pdf",
      "recortar-pdf", "cambiar-tamano-pagina-pdf", "varias-paginas-por-hoja", "folleto-pdf", "cortar-paginas-por-la-mitad",
      "montar-pdf", "superponer-pdf", "marcadores-pdf", "imprimir-pdf"] },
    { id: "editar", es: "Editar y rellenar", en: "Edit and fill", tools: [
      "editar-pdf", "rellenar-pdf", "anotar-pdf", "marca-de-agua-pdf", "escribir-pdf", "hacer-pdf-rellenable", "crear-formulario-pdf",
      "aplanar-pdf", "solicitud-de-empleo-pdf", "lector-pdf", "comparar-pdf", "buscar-en-pdf", "copiar-de-pdf"] },
    { id: "optimizar", es: "Optimizar y reparar", en: "Optimise and repair", tools: [
      "comprimir-pdf", "ocr-pdf", "reparar-pdf", "optimizar-pdf-web", "pdf-a-pdfa", "validar-pdfa", "pdf-escala-de-grises",
      "pdf-modo-oscuro", "rasterizar-pdf", "preferencias-visor-pdf", "metadatos-pdf"] },
    { id: "seguridad", es: "Seguridad", en: "Security", tools: [
      "proteger-pdf", "desbloquear-pdf", "redactar-pdf", "eliminar-metadatos-pdf"] },
  ],
  office: [
    { id: "a-pdf", es: "Documentos a PDF", en: "Documents to PDF", tools: [
      "word-a-pdf", "excel-a-pdf", "ppt-a-pdf", "convertir-a-pdf", "html-a-pdf", "web-a-pdf", "txt-a-pdf", "markdown-a-pdf", "csv-a-pdf",
      "odt-a-pdf", "ods-a-pdf", "odp-a-pdf", "odg-a-pdf", "rtf-a-pdf", "svg-a-pdf", "latex-a-pdf", "word-a-pdf-accesible", "udf-a-pdf"] },
    { id: "otros-programas", es: "Pages, Keynote, Visio…", en: "Pages, Keynote, Visio…", tools: [
      "pages-a-pdf", "keynote-a-pdf", "numbers-a-pdf", "visio-a-pdf", "publisher-a-pdf", "drawio-a-pdf", "drawio-a-png"] },
    { id: "entre-formatos", es: "Entre formatos de oficina", en: "Between office formats", tools: [
      "docx-a-odt", "odt-a-docx", "docx-a-markdown", "markdown-a-docx", "docx-a-html", "html-a-docx", "xlsx-a-csv", "csv-a-xlsx",
      "ods-a-xlsx", "xlsx-a-ods"] },
    { id: "libros", es: "Libros electrónicos", en: "E-books", tools: [
      "epub-a-pdf", "mobi-a-pdf", "azw3-a-pdf", "fb2-a-pdf", "epub-a-mobi", "epub-a-azw3", "mobi-a-epub", "azw3-a-epub"] },
  ],
  image: [
    { id: "convertir", es: "Convertir imágenes", en: "Convert images", tools: [
      "convertir-imagen", "heic-a-jpg", "png-a-jpg", "jpg-a-png", "webp-a-jpg", "webp-a-png", "jpg-a-webp", "png-a-webp", "heic-a-png",
      "avif-a-jpg", "jpg-a-avif", "gif-a-png", "bmp-a-jpg", "tiff-a-jpg", "raw-a-jpg", "psd-a-png", "png-a-ico", "pptx-a-imagenes"] },
    { id: "editar", es: "Editar y optimizar", en: "Edit and optimise", tools: [
      "comprimir-imagen", "redimensionar-imagen", "quitar-fondo", "quitar-metadatos-foto", "imagen-a-base64"] },
    { id: "crear", es: "Crear y escanear", en: "Create and scan", tools: [
      "generar-codigo-qr", "leer-codigo-qr", "crear-collage", "crear-tarjeta", "crear-favicon", "captura-web"] },
    { id: "vectores", es: "Vectores y diagramas", en: "Vectors and diagrams", tools: [
      "svg-a-png", "png-a-svg", "jpg-a-svg", "svg-a-jpg", "mermaid-a-svg", "mermaid-a-png"] },
  ],
  audio: [
    { id: "a-mp3", es: "Convertir a MP3", en: "Convert to MP3", tools: [
      "m4a-a-mp3", "wav-a-mp3", "mp4-a-mp3", "ogg-a-mp3", "opus-a-mp3", "flac-a-mp3", "aac-a-mp3", "wma-a-mp3", "amr-a-mp3",
      "aiff-a-mp3", "midi-a-mp3"] },
    { id: "editar", es: "Editar audio", en: "Edit audio", tools: [
      "cortar-audio", "unir-audios", "normalizar-volumen", "cambiar-velocidad-audio", "transcribir-audio"] },
    { id: "wav-partituras", es: "WAV y partituras", en: "WAV and sheet music", tools: [
      "mp3-a-wav", "ogg-a-wav", "midi-a-wav", "midi-a-pdf", "musicxml-a-pdf"] },
  ],
  video: [
    { id: "convertir", es: "Convertir vídeo", en: "Convert video", tools: [
      "mov-a-mp4", "mkv-a-mp4", "avi-a-mp4", "webm-a-mp4", "mp4-a-webm", "video-a-gif", "gif-a-mp4", "pptx-a-video"] },
    { id: "editar", es: "Editar vídeo", en: "Edit video", tools: ["comprimir-video", "recortar-video", "rotar-video", "quitar-audio-video"] },
    { id: "subtitulos", es: "Subtítulos", en: "Subtitles", tools: ["video-a-subtitulos", "srt-a-vtt", "vtt-a-srt", "ass-a-srt"] },
  ],
  ai: [
    { id: "estudiar", es: "Leer y estudiar", en: "Read and study", tools: [
      "resumir-pdf", "chat-pdf", "generador-de-preguntas", "pdf-a-fichas", "pdf-a-presentacion", "pdf-a-audio", "resumir-reunion"] },
    { id: "traducir", es: "Traducir", en: "Translate", tools: [
      "traducir-pdf", "traducir-word", "traducir-excel", "traducir-powerpoint", "traducir-subtitulos"] },
    { id: "extraer", es: "Extraer texto y datos", en: "Extract text and data", tools: [
      "imagen-a-texto", "manuscrito-a-texto", "imagen-a-excel", "ticket-a-excel"] },
  ],
  data: [
    { id: "estructurados", es: "CSV, JSON, XML y YAML", en: "CSV, JSON, XML and YAML", tools: [
      "csv-a-json", "json-a-csv", "excel-a-json", "xml-a-json", "json-a-xml", "yaml-a-json", "json-a-yaml", "arreglar-codificacion-csv"] },
    { id: "mapas", es: "Mapas y GPS", en: "Maps and GPS", tools: [
      "gpx-a-kml", "kml-a-gpx", "kmz-a-gpx", "gpx-a-geojson", "geojson-a-kml", "shp-a-geojson", "shp-a-kml", "csv-a-kml", "tcx-a-gpx",
      "fit-a-gpx", "fit-a-csv"] },
    { id: "contactos", es: "Contactos y calendarios", en: "Contacts and calendars", tools: [
      "vcf-a-csv", "csv-a-vcf", "vcf-a-excel", "ics-a-csv", "csv-a-ics", "ics-a-excel"] },
    { id: "archivos", es: "Archivos comprimidos", en: "Archives", tools: [
      "extraer-archivo-online", "rar-a-zip", "7z-a-zip", "tar-a-zip", "generar-contrasena"] },
    { id: "fuentes", es: "Fuentes tipográficas", en: "Fonts", tools: [
      "ttf-a-woff2", "otf-a-woff2", "woff2-a-ttf", "woff-a-ttf", "ttf-a-otf", "otf-a-ttf"] },
    { id: "correo", es: "Correo", en: "Email", tools: ["mbox-a-pdf", "mbox-a-eml", "pst-a-pdf", "pst-a-mbox"] },
  ],
  "3d": [
    { id: "mallas", es: "Convertir mallas", en: "Convert meshes", tools: [
      "convertir-modelo-3d", "stl-a-obj", "obj-a-stl", "stl-a-3mf", "3mf-a-stl", "obj-a-3mf", "3mf-a-obj", "glb-a-stl", "stl-a-glb",
      "gltf-a-stl", "fbx-a-stl", "fbx-a-obj", "dae-a-stl", "3ds-a-stl", "stl-a-ply", "ply-a-stl", "stl-ascii-a-binario", "amf-a-stl",
      "stl-a-amf", "amf-a-3mf", "wrl-a-stl", "stl-a-wrl", "x3d-a-stl", "stl-a-x3d", "stl-a-usdz", "obj-a-usdz", "comprimir-glb"] },
    { id: "cad", es: "CAD: STEP, IGES, DWG", en: "CAD: STEP, IGES, DWG", tools: [
      "step-a-stl", "stp-a-stl", "step-a-3mf", "step-a-obj", "step-a-glb", "iges-a-stl", "igs-a-step", "brep-a-stl", "stl-a-step",
      "obj-a-step", "dwg-a-dxf", "dwg-a-pdf", "scad-a-stl", "scad-a-3mf"] },
    { id: "ver", es: "Ver y analizar", en: "View and analyse", tools: ["visor-3d", "visor-gcode", "render-modelo-3d", "analizar-stl"] },
    { id: "editar", es: "Reparar y editar", en: "Repair and edit", tools: [
      "reparar-stl", "reducir-poligonos", "escalar-modelo-3d", "cambiar-unidades-stl", "cortar-modelo-3d", "separar-piezas",
      "unir-modelos"] },
    { id: "crear", es: "Crear modelos", en: "Create models", tools: [
      "texto-a-stl", "logo-a-stl", "imagen-a-stl", "litofania", "svg-a-stl", "dxf-a-stl", "mapa-de-alturas-a-stl"] },
    { id: "gcode", es: "Impresión 3D (G-code)", en: "3D printing (G-code)", tools: [
      "analizar-gcode", "gcode-a-imagen", "extraer-miniatura-gcode", "gcode-a-bgcode", "bgcode-a-gcode", "extraer-gcode-3mf"] },
  ],
  sign: [
    { id: "firmar", es: "Firmar y compartir", en: "Sign and share", tools: ["firmar-pdf", "solicitar-firmas", "compartir-pdf"] },
    { id: "verificar", es: "Verificar y abrir firmados", en: "Verify and open signed files", tools: [
      "verificar-firmas-pdf", "verificar-firma", "p7m-a-pdf", "xsig-a-pdf", "csig-a-pdf"] },
  ],
  invoice: [
    { id: "crear", es: "Crear facturas", en: "Create invoices", tools: [
      "crear-factura", "crear-factura-electronica", "pdf-a-factura-electronica"] },
    { id: "abrir", es: "Validar y ver", en: "Validate and view", tools: [
      "validar-factura-electronica", "factura-electronica-a-pdf", "facturae-a-pdf", "ubl-a-pdf", "cii-a-pdf"] },
  ],
};

/** `paid`: usa mucho servidor y va con el pase de 24 h (D-273). */
export type MenuTool = { slug: string; href: string; name: string; summary: string; where: string; paid: boolean; from: string; to: string };

/** Formato de entrada y de salida que se enseña en la tarjeta («PDF → DOCX»); el ZIP de varios resultados no cuenta. */
export function formatsOf(inputs: string[], outputs: string[]): { from: string; to: string } {
  const from = (inputs[0] ?? "").toUpperCase();
  const to = (outputs.find((o) => o !== "zip") ?? outputs[0] ?? "").toUpperCase();
  return { from, to: to === from ? "" : to };
}
export type MenuGroup = { id: string; label: string; tools: MenuTool[] };

const BY_SLUG = new Map(TOOLS.map((tool) => [tool.slug_es, tool]));

/** Secciones de una categoría con sus herramientas activas; las secciones que se quedan vacías no se pintan. */
export function categoryGroups(category: string, locale: Locale): MenuGroup[] {
  return (MENU_GROUPS[category] ?? [])
    .map((group) => ({
      id: group.id,
      label: group[locale],
      tools: group.tools
        .map((slug) => BY_SLUG.get(slug))
        .filter((tool) => tool && !tool.canonical_of && !disabledByEnv(tool.slug_es))
        .map((tool) => ({
          slug: tool!.slug_es,
          href: toolPath(locale, tool!),
          name: nameOf(tool!, locale),
          summary: summaryOf(tool!, locale),
          where: tool!.where,
          paid: tool!.where !== "client" && (tool!.cost_class !== "light" || Boolean(tool!.needs_video)),
          ...formatsOf(tool!.inputs, tool!.outputs),
        })),
    }))
    .filter((group) => group.tools.length);
}

/** Los formatos que más aparecen en una categoría (para la ilustración de su apartado). */
export function topFormats(category: string, n = 6): string[] {
  const count = new Map<string, number>();
  for (const tool of TOOLS) {
    if (tool.category !== category || tool.canonical_of) continue;
    for (const f of new Set([...tool.inputs, ...tool.outputs])) {
      if (f === "zip") continue;
      count.set(f, (count.get(f) ?? 0) + 1);
    }
  }
  return [...count].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, n).map(([f]) => f.toUpperCase());
}
