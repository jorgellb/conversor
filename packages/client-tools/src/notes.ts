// Avisos de resultado de las herramientas de navegador en el idioma de la página (D-42, D-86 y D-151).
// Las herramientas de 7.11 y 7.23 llevan sus textos en su propio módulo; aquí van los de las herramientas de PDF de F1 y F2.
export type Locale = "es" | "en";

const pages = (list: number[]) => list.map((p) => p + 1).join(", ");

export const NOTES = {
  es: {
    annotations: (n: number) => `${n} anotaciones estándar, editables en otros lectores.`,
    changes: (n: number) => `${n} cambios entre los dos documentos.`,
    printActualSize: "Al imprimir, elige «Tamaño real» en el diálogo.",
    printManualDuplex: "Imprime los anversos, da la vuelta al montón sin girarlo e imprime los reversos. Elige «Tamaño real».",
    resizeLosesLinks: "Los enlaces y los campos de formulario no se conservan al cambiar el tamaño.",
    bookletPdf: "Imprime a doble cara volteando por el borde corto y dobla las hojas por la mitad.",
    bookletManual: "Imprime primero los anversos, da la vuelta al montón sin girarlo e imprime los reversos; después dobla las hojas por la mitad.",
    blankNotCropped: (page: number) => `Página ${page + 1}: en blanco, no se recorta.`,
    noAnnotations: (file: string) => `${file}: no tenía anotaciones que aplanar.`,
    pageOverSize: "Alguna página supera por sí sola el tamaño máximo.",
    watermarkNotFlattened: "No se ha podido aplanar en este navegador; la marca de agua se ha añadido sin aplanar.",
    xfaRemoved: "El formulario tenía una capa XFA, que no es compatible: se han rellenado sus campos AcroForm.",
    xfaRemovedDesign: "El PDF tenía una capa XFA, que no es compatible: se ha quitado y los campos son AcroForm.",
    signatureFields: (n: number) => `${n} campo(s) de firma añadidos en el servidor con pyHanko; se pueden firmar con «Firmar PDF».`,
    unknownFields: (names: string[]) => `Campos que no existen en el PDF: ${names.join(", ")}`,
    notFlattened: "Algunos campos no se han podido aplanar y siguen siendo editables.",
    imagesToPng: "Las imágenes WEBP, GIF y BMP se han convertido a PNG sin pérdida.",
    results: (n: number) => `${n} resultados.`,
    rasterized: (list: number[]) => `Páginas convertidas en imagen: ${pages(list)}. Su texto ya no se puede seleccionar; puedes pasarlas por OCR.`,
    removedUnder: (list: number[]) => `Se ha eliminado el contenido bajo las áreas en las páginas ${pages(list)}; el resto del texto sigue siendo seleccionable.`,
    objectsAsImage: (n: number) => `${n} dibujo(s), imagen(es) o grupo(s) que tocaban un área se han convertido en imagen para borrar su parte tapada.`,
    annotationsRemoved: (n: number) => `Se han quitado ${n} anotación(es), enlace(s) o campo(s) que tocaban un área.`,
    metadataRemoved: "Se han quitado los metadatos del documento.",
    textAsImage: (list: number[]) => `Páginas ${pages(list)}: el contenido bajo las áreas se ha eliminado, pero parte del texto de alrededor estaba en un mismo grupo con lo tapado y se ha convertido en imagen con él; ese texto ya no se puede seleccionar. Puedes pasar esas páginas por OCR.`,
    structureRemoved: "Se han quitado las etiquetas de accesibilidad y la capa XFA del documento, que podían repetir el texto tapado.",
    attachmentsRemoved: (n: number) => `Se han quitado ${n} archivo(s) adjunto(s) del PDF, que podían repetir el texto tapado.`,
    scrubbed: (n: number) => `Se ha tapado el texto redactado en ${n} texto(s) del archivo que no se ven en la página (marcadores, comentarios, enlaces o campos).`,
  },
  en: {
    annotations: (n: number) => `${n} standard annotations, editable in other readers.`,
    changes: (n: number) => `${n} changes between the two documents.`,
    printActualSize: "When printing, choose “Actual size” in the dialog.",
    printManualDuplex: "Print the fronts, turn the stack over without rotating it and print the backs. Choose “Actual size”.",
    resizeLosesLinks: "Links and form fields are not kept when the size changes.",
    bookletPdf: "Print double-sided flipping on the short edge and fold the sheets in half.",
    bookletManual: "Print the fronts first, turn the stack over without rotating it and print the backs; then fold the sheets in half.",
    blankNotCropped: (page: number) => `Page ${page + 1}: blank, not cropped.`,
    noAnnotations: (file: string) => `${file}: it had no annotations to flatten.`,
    pageOverSize: "Some page is larger than the maximum size on its own.",
    watermarkNotFlattened: "This browser could not flatten the file; the watermark was added without flattening.",
    xfaRemoved: "The form had an XFA layer, which is not supported: its AcroForm fields were filled in.",
    xfaRemovedDesign: "The PDF had an XFA layer, which is not supported: it was removed and the fields are AcroForm.",
    signatureFields: (n: number) => `${n} signature field(s) added on the server with pyHanko; they can be signed with “Sign PDF”.`,
    unknownFields: (names: string[]) => `Fields that do not exist in the PDF: ${names.join(", ")}`,
    notFlattened: "Some fields could not be flattened and are still editable.",
    imagesToPng: "WEBP, GIF and BMP images were converted to lossless PNG.",
    results: (n: number) => `${n} results.`,
    rasterized: (list: number[]) => `Pages turned into images: ${pages(list)}. Their text can no longer be selected; you can run them through OCR.`,
    removedUnder: (list: number[]) => `The content under the areas was removed on pages ${pages(list)}; the rest of the text can still be selected.`,
    objectsAsImage: (n: number) => `${n} drawing(s), image(s) or group(s) touching an area were turned into an image to erase their covered part.`,
    annotationsRemoved: (n: number) => `${n} annotation(s), link(s) or field(s) touching an area were removed.`,
    metadataRemoved: "The document metadata was removed.",
    textAsImage: (list: number[]) => `Pages ${pages(list)}: the content under the areas was removed, but part of the text around it was in the same group as the covered content and was turned into an image with it; that text can no longer be selected. You can run those pages through OCR.`,
    structureRemoved: "The document's accessibility tags and XFA layer were removed, as they could repeat the covered text.",
    attachmentsRemoved: (n: number) => `${n} file attachment(s) were removed from the PDF, as they could repeat the covered text.`,
    scrubbed: (n: number) => `The redacted text was covered in ${n} piece(s) of text in the file that are not shown on the page (bookmarks, comments, links or fields).`,
  },
} satisfies Record<Locale, Record<string, unknown>>;

/** Textos de aviso del idioma pedido (español si no llega o no se conoce). */
export function notesFor(locale?: string): (typeof NOTES)["es"] {
  return NOTES[locale === "en" ? "en" : "es"];
}
