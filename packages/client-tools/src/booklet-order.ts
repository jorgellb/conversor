// Orden de imposición de folleto-pdf (A.4), sin dependencias (ni pdf-lib): lo usan el motor y la vista previa de la web.

/**
 * Orden de imposición de un cuadernillo de `pages` páginas (múltiplo de 4), con índices desde 0:
 * cada elemento es una cara de hoja [izquierda, derecha]. Encuadernación a la izquierda.
 */
export function bookletOrder(pages: number, binding: "izquierda" | "derecha" = "izquierda"): [number, number][] {
  if (pages % 4 !== 0) throw new RangeError("El cuadernillo debe tener un múltiplo de 4 páginas");
  const sides: [number, number][] = [];
  for (let s = 0; s < pages / 4; s += 1) {
    const front: [number, number] = [pages - 1 - 2 * s, 2 * s];
    const back: [number, number] = [2 * s + 1, pages - 2 - 2 * s];
    sides.push(binding === "izquierda" ? front : [front[1], front[0]], binding === "izquierda" ? back : [back[1], back[0]]);
  }
  return sides;
}

/** Posiciones lógicas tras añadir páginas en blanco hasta un múltiplo de 4 (`null` = en blanco). */
export function padToFour(count: number, keepBackCover: boolean): (number | null)[] {
  const total = Math.ceil(count / 4) * 4;
  const blanks = total - count;
  const list: (number | null)[] = Array.from({ length: count }, (_, i) => i);
  if (!blanks) return list;
  if (keepBackCover && count > 1) return [...list.slice(0, -1), ...Array(blanks).fill(null), count - 1];
  return [...list, ...Array(blanks).fill(null)];
}

