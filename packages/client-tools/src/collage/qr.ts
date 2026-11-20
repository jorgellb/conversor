// crear-tarjeta (F6-N2, D-232): códigos QR de la tarjeta con qrcode-generator (MIT), en UTF-8 y corrección M, como un solo
// trazado de módulos que pintan igual el editor (Konva), svgpdf y resvg.
import qrcode from "qrcode-generator";

export const QR_MAX = 900;
const QUIET = 4;

export interface QrModules {
  /** Trazado en unidades de módulo, con la zona de silencio incluida (de 0 a `size`). */
  d: string;
  size: number;
}

const cache = new Map<string, QrModules>();

function utf8(text: string): number[] {
  return [...new TextEncoder().encode(text)];
}

export function qrModules(data: string): QrModules {
  const text = data.slice(0, QR_MAX) || " ";
  const hit = cache.get(text);
  if (hit) return hit;
  const qr = qrcode(0, "M");
  // qrcode-generator codifica cada carácter con su código: se le dan los bytes UTF-8 para que lean bien los acentos.
  qr.addData(String.fromCharCode(...utf8(text)), "Byte");
  qr.make();
  const count = qr.getModuleCount();
  const parts: string[] = [];
  for (let r = 0; r < count; r += 1) {
    let c = 0;
    while (c < count) {
      if (!qr.isDark(r, c)) {
        c += 1;
        continue;
      }
      const start = c;
      while (c < count && qr.isDark(r, c)) c += 1;
      parts.push(`M${start + QUIET} ${r + QUIET}h${c - start}v1h-${c - start}Z`);
    }
  }
  const out = { d: parts.join(""), size: count + 2 * QUIET };
  if (cache.size > 50) cache.clear();
  cache.set(text, out);
  return out;
}
