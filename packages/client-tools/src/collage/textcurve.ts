// crear-tarjeta (F6-N2, D-232): texto en curva. Cada letra se coloca en un arco con su giro, a partir de su avance real
// (fontkit en el worker, measureText en el editor): así sale igual en el PDF, la imagen y la pantalla.

export interface CurvedGlyph {
  ch: string;
  x: number;
  y: number;
  /** Giro en grados (horario). */
  angle: number;
}

export interface CurveBox {
  x: number;
  y: number;
  w: number;
  size: number;
  curve: number;
}

/** Alto de la caja de un texto en curva (lo que baja o sube el arco más la letra). */
export function curveHeight(w: number, size: number, curve: number): number {
  return Math.abs(Math.max(-1, Math.min(1, curve))) * (w / 2) + size * 1.3;
}

/** Posición de cada letra en el arco; `advance` da el avance en mm de cada carácter. */
export function curvedGlyphs(text: string, box: CurveBox, advance: (ch: string) => number): CurvedGlyph[] {
  const chars = [...text.replace(/\s*\n\s*/g, " ")];
  const c = Math.max(-1, Math.min(1, box.curve));
  const widths = chars.map((ch) => Math.max(0, advance(ch)));
  const total = widths.reduce((a, b) => a + b, 0);
  const s = Math.abs(c) * (box.w / 2);
  const cx = box.x + box.w / 2;
  if (s < 0.05) {
    // Casi recto: en línea, centrado.
    let at = cx - total / 2;
    return chars.map((ch, i) => {
      const g = { ch, x: at + widths[i] / 2, y: box.y + box.size * 0.8, angle: 0 };
      at += widths[i];
      return g;
    });
  }
  const R = (box.w * box.w) / 4 / (2 * s) + s / 2;
  // Si el texto es más largo que media circunferencia, se juntan las letras para que quepa (D-235).
  const room = Math.PI * R * 0.98;
  if (total > room) {
    const k = room / total;
    for (let i = 0; i < widths.length; i += 1) widths[i] *= k;
  }
  const fitted = Math.min(total, room);
  const up = c > 0;
  // Arco hacia arriba: el centro queda debajo del punto más alto; sonrisa: encima del más bajo.
  const top = box.y + box.size * 0.8;
  const cy = up ? top + R : top + s - R;
  let at = -fitted / 2;
  return chars.map((ch, i) => {
    const u = at + widths[i] / 2;
    at += widths[i];
    const theta = Math.max(-Math.PI, Math.min(Math.PI, u / R));
    return up
      ? { ch, x: cx + R * Math.sin(theta), y: cy - R * Math.cos(theta), angle: (theta * 180) / Math.PI }
      : { ch, x: cx + R * Math.sin(theta), y: cy + R * Math.cos(theta), angle: (-theta * 180) / Math.PI };
  });
}
