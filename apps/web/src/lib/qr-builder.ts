"use client";

// generar-codigo-qr (A.1): compone el SVG con qr-code-styling en la página (necesita DOM). El worker lo convierte en
// PNG o PDF y lo lee con zxing-cpp para comprobarlo.
import { QrInputError, checkMode, qrPayload, toSjisBytes, type QrContent, type QrMode } from "@conversor/client-tools/qrdata";
import { normalizeSvgRefs } from "@conversor/client-tools/svgrefs";
import type { Gradient, Options } from "qr-code-styling";

export type QrValues = Record<string, unknown>;

const DOTS = { cuadrado: "square", puntos: "dots", redondeado: "rounded", muy_redondeado: "extra-rounded", elegante: "classy", elegante_redondeado: "classy-rounded" } as const;
const OUTER = { cuadrado: "square", punto: "dot", muy_redondeado: "extra-rounded" } as const;
const INNER = { cuadrado: "square", punto: "dot" } as const;
const MODES = { byte: "Byte", numerico: "Numeric", alfanumerico: "Alphanumeric", kanji: "Kanji" } as const;
type Correction = "L" | "M" | "Q" | "H";

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
const color = (v: unknown, fallback: string) => (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v : fallback);

function gradient(v: QrValues, key: string, base: string): Gradient | undefined {
  const kind = v[`${key}_degradado`];
  if (kind !== "lineal" && kind !== "radial") return undefined;
  return {
    type: kind === "lineal" ? "linear" : "radial",
    rotation: (Number(v[`${key}_angulo`] ?? 0) * Math.PI) / 180,
    colorStops: [{ offset: 0, color: base }, { offset: 1, color: color(v[`${key}_color2`], base) }],
  };
}

/** Matriz del QR con qrcode-generator y Shift_JIS propio (qr-code-styling no trae el modo Kanji). */
async function matrix(payload: string, typeNumber: number, correction: Correction, mode: QrMode) {
  const { default: qrcode } = await import("qrcode-generator");
  // Como qr-code-styling: el modo Byte en UTF-8. El Kanji usa la tabla Shift_JIS propia.
  qrcode.stringToBytes = qrcode.stringToBytesFuncs["UTF-8"];
  qrcode.stringToBytesFuncs.SJIS = (s: string) => toSjisBytes(s);
  const qr = qrcode(typeNumber as Parameters<typeof qrcode>[0], correction);
  try {
    qr.addData(payload, MODES[mode]);
    qr.make();
  } catch {
    throw new QrInputError(typeNumber ? "version_too_small" : "too_long", { version: String(typeNumber), correction });
  }
  return qr;
}

async function styled(options: Partial<Options>, kanjiQr: Awaited<ReturnType<typeof matrix>> | null): Promise<string> {
  const { default: QRCodeStyling } = await import("qr-code-styling");
  let qr: InstanceType<typeof QRCodeStyling>;
  if (kanjiQr) {
    // Sin datos, qr-code-styling no crea su matriz; se le da la del modo Kanji y se dibuja.
    qr = new QRCodeStyling({ ...options, data: "" });
    qr._options.data = String(options.data);
    qr._qr = kanjiQr as unknown as NonNullable<typeof qr._qr>;
    qr._setupSvg();
  } else {
    qr = new QRCodeStyling(options);
  }
  const blob = await qr.getRawData("svg");
  if (!blob) throw new QrInputError("too_long", {});
  return (blob as Blob).text();
}

/**
 * qr-code-styling guarda el modo Byte en Latin-1 (cada carácter, un byte: «€» o «漢» se estropean). Se le pasa el
 * texto ya convertido a bytes UTF-8, uno por carácter, y los lectores lo reconocen como UTF-8.
 */
export function utf8Binary(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let out = "";
  for (let i = 0; i < bytes.length; i += 0x2000) out += String.fromCharCode(...bytes.subarray(i, i + 0x2000));
  return out;
}

export interface BuiltQr {
  svg: string;
  payload: string;
  correction: Correction;
}

/**
 * SVG final: el de qr-code-styling con la zona de silencio (2 módulos) o, si hay borde, dentro de un marco con su
 * espacio. Con logotipo la corrección es siempre H (A.1).
 */
export async function buildQrSvg(v: QrValues, logo: string | null): Promise<BuiltQr> {
  const payload = qrPayload(v as unknown as QrContent);
  const mode = (String(v.modo ?? "byte") in MODES ? String(v.modo ?? "byte") : "byte") as QrMode;
  checkMode(payload, mode);
  const size = clamp(Math.round(Number(v.tamano) || 500), 100, 10000);
  const border = v.borde ? clamp(Math.round(Number(v.borde_grosor) || 0), 1, 200) : 0;
  const gap = v.borde ? clamp(Math.round(Number(v.borde_espaciado) || 0), 0, 500) : 0;
  const inner = size - 2 * (border + gap);
  if (inner < 60) throw new QrInputError("border_too_big", {});
  const correction: Correction = logo ? "H" : (["L", "M", "Q", "H"].includes(String(v.correccion)) ? String(v.correccion) : "Q") as Correction;
  const typeNumber = clamp(Math.trunc(Number(v.version) || 0), 0, 40);
  const qr = await matrix(payload, typeNumber, correction, mode);
  const margin = border + gap ? 0 : Math.round((2 * inner) / (qr.getModuleCount() + 4));
  const circle = v.forma === "circulo";
  const bg = color(v.fondo, "#FFFFFF");
  const dots = color(v.modulos, "#000000");
  const outer = color(v.ojos_exteriores, "#000000");
  const innerEye = color(v.ojos_interiores, "#000000");
  const options: Partial<Options> = {
    type: "svg",
    width: inner,
    height: inner,
    margin,
    data: mode === "byte" ? utf8Binary(payload) : payload,
    shape: circle ? "circle" : "square",
    qrOptions: { typeNumber: typeNumber as NonNullable<Options["qrOptions"]>["typeNumber"], mode: MODES[mode], errorCorrectionLevel: correction },
    dotsOptions: { type: DOTS[v.forma_modulos as keyof typeof DOTS] ?? "square", color: dots, gradient: gradient(v, "modulos", dots) },
    cornersSquareOptions: { type: OUTER[v.forma_ojos_exteriores as keyof typeof OUTER] ?? "square", color: outer, gradient: gradient(v, "ojos_exteriores", outer) },
    cornersDotOptions: { type: INNER[v.forma_ojos_interiores as keyof typeof INNER] ?? "square", color: innerEye, gradient: gradient(v, "ojos_interiores", innerEye) },
    backgroundOptions: { color: bg, gradient: gradient(v, "fondo", bg), round: circle ? 1 : 0 },
    ...(logo
      ? {
        image: logo,
        imageOptions: {
          hideBackgroundDots: Boolean(v.logo_quitar_fondo),
          imageSize: clamp(Number(v.logo_tamano) || 0.4, 0.1, 1),
          margin: clamp(Math.round(Number(v.logo_margen) || 0), 0, 100),
          // El logotipo ya es un data URL: así qr-code-styling no lo vuelve a descargar con fetch (CSP connect-src).
          saveAsBlob: false,
        },
      }
      : {}),
  };
  const raw = await styled(options, mode === "kanji" ? qr : null);
  const open = /<svg[^>]*>/.exec(raw);
  const close = raw.lastIndexOf("</svg>");
  if (!open || close < 0) throw new QrInputError("too_long", {});
  const body = raw.slice(open.index + open[0].length, close);
  const head = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">`;
  let svg: string;
  if (!border && !gap) {
    svg = `${head}${body}</svg>`;
  } else {
    const stroke = color(v.borde_color, "#000000");
    const frame = circle
      ? `<circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - border / 2}" fill="${bg}" stroke="${stroke}" stroke-width="${border}"/>`
      : `<rect x="${border / 2}" y="${border / 2}" width="${size - border}" height="${size - border}" fill="${bg}" stroke="${stroke}" stroke-width="${border}"/>`;
    svg = `${head}${frame}<g transform="translate(${border + gap} ${border + gap})">${body}</g></svg>`;
  }
  return { svg: normalizeSvgRefs(svg), payload, correction };
}

/** Logotipo como PNG en data URL (lado mayor de 1024 px como mucho): el SVG, el PNG y el PDF lo llevan igual. */
export async function logoToPng(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const w0 = img.naturalWidth || 512;
    const h0 = img.naturalHeight || 512;
    const scale = Math.min(1, 1024 / Math.max(w0, h0));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w0 * scale));
    canvas.height = Math.max(1, Math.round(h0 * scale));
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png");
  } finally {
    URL.revokeObjectURL(url);
  }
}
