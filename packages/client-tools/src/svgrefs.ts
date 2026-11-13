// Sin dependencias: lo usan el worker (resvg) y la página (vista previa de generar-codigo-qr).

/**
 * resvg no resuelve las referencias entre comillas (`url('#a')`, `url("#a")`), que sí usan qr-code-styling y otros
 * programas: sin este arreglo pinta los degradados y recortes en negro. Se quitan las comillas.
 */
export function normalizeSvgRefs(svg: string): string {
  return svg.replace(/url\(\s*(?:'|"|&quot;|&apos;|&#39;|&#34;)(#[^'"&)]*)(?:'|"|&quot;|&apos;|&#39;|&#34;)\s*\)/g, "url($1)");
}
