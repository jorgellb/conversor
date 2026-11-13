import { readFileSync } from "node:fs";
import path from "node:path";

import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { readIcoDirectory } from "../src/encoders";
import { exifOrientation, extractExif } from "../src/exif";
import { CLIENT_TOOLS, runClientTool, type ClientEnv } from "../src/index";
import type { FontKind, FontStyle } from "../src/pdfutil";
import { sniffImage } from "../src/sniff";
import { decodeWasm } from "../src/wasmcodecs";
import { b64 } from "./images.fixture";
import { JPEG_GPS, PNG_GPS, TIFF_2P } from "./images-f5.fixture";
import { nodeCodec, readImage, type NodeCodecLog } from "./image-node";
import { nodeWasm } from "./wasm-node";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const FILES: Record<FontKind, Record<FontStyle, string>> = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
};

function env(log?: NodeCodecLog, extra: Partial<ClientEnv> = {}): ClientEnv {
  return {
    codec: nodeCodec(log),
    wasm: nodeWasm,
    fonts: async (kind, style = "regular") => new Uint8Array(readFileSync(path.join(FONTS, `${FILES[kind][style]}.ttf`))),
    ...extra,
  };
}

const JPG = { name: "foto.jpg", bytes: b64(JPEG_GPS) };
const PNG = { name: "logo.png", bytes: b64(PNG_GPS) };
const SVG = (body: string, w = 40, h = 20) =>
  new TextEncoder().encode(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`);

const CONVERT = { calidad: 80, fondo: "#FFFFFF", sin_perdida: false, velocidad: "rapida", tamanos_ico: [16, 32, 48, 256], ajuste: "encajar", conservar_metadatos: false, paginas: "todas" };

describe("conversiones de imagen (7.11)", () => {
  it("registra todas las herramientas nuevas como de navegador", () => {
    for (const slug of ["jpg-a-png", "webp-a-png", "gif-a-png", "jpg-a-webp", "png-a-webp", "avif-a-jpg", "bmp-a-jpg", "tiff-a-jpg",
      "jpg-a-avif", "png-a-ico", "convertir-imagen", "svg-a-png", "svg-a-jpg", "crear-favicon", "quitar-metadatos-foto", "imagen-a-base64"]) {
      expect(CLIENT_TOOLS).toContain(slug);
    }
  });

  it("jpg-a-png aplica la orientación EXIF y, si se pide, conserva el EXIF con la orientación ya puesta", async () => {
    const plain = await runClientTool("jpg-a-png", [JPG], { conservar_metadatos: false }, env());
    expect(plain.outputs[0].name).toBe("foto.png");
    expect(sniffImage(plain.outputs[0].bytes)).toBe("png");
    const img = await readImage(plain.outputs[0].bytes);
    expect([img.width, img.height]).toEqual([48, 64]); // la foto 64×48 con orientación 6 sale en vertical
    expect(extractExif(plain.outputs[0].bytes)).toBeNull();
    const kept = await runClientTool("jpg-a-png", [JPG], { conservar_metadatos: true }, env());
    const exif = extractExif(kept.outputs[0].bytes);
    expect(exifOrientation(exif)).toBe(1);
    expect(new TextDecoder("latin1").decode(exif!)).toContain("Camara de prueba");
  });

  it("png-a-webp con pérdida y sin pérdida conserva la transparencia", async () => {
    for (const sin_perdida of [false, true]) {
      const res = await runClientTool("png-a-webp", [PNG], { calidad: 80, sin_perdida, conservar_metadatos: false }, env());
      expect(res.outputs[0].name).toBe("logo.webp");
      const back = await decodeWasm(nodeWasm, "webp", res.outputs[0].bytes);
      expect([back.width, back.height]).toEqual([40, 30]);
      expect(back.data[(10 * 40 + 35) * 4 + 3]).toBe(0); // mitad derecha transparente
      expect(back.data[(10 * 40 + 5) * 4 + 3]).toBe(255);
      if (sin_perdida) {
        const src = await readImage(PNG.bytes);
        expect(back.data[(10 * 40 + 5) * 4]).toBe(src.data[(10 * 40 + 5) * 4]);
      }
    }
  });

  it("jpg-a-webp con metadatos inserta el EXIF en un WebP extendido", async () => {
    const res = await runClientTool("jpg-a-webp", [JPG], { calidad: 80, sin_perdida: false, conservar_metadatos: true }, env());
    const out = res.outputs[0].bytes;
    expect(new TextDecoder("latin1").decode(out.subarray(12, 16))).toBe("VP8X");
    expect(out[20] & 0x08).toBe(0x08);
    expect(exifOrientation(extractExif(out))).toBe(1);
    const back = await decodeWasm(nodeWasm, "webp", out);
    expect([back.width, back.height]).toEqual([48, 64]);
  });

  it("jpg-a-avif y avif-a-jpg (el navegador «sin AVIF» pasa a jSquash)", async () => {
    const avif = await runClientTool("jpg-a-avif", [JPG], { calidad: 60, velocidad: "rapida" }, env());
    expect(avif.outputs[0].name).toBe("foto.avif");
    expect(sniffImage(avif.outputs[0].bytes)).toBe("avif");
    const decoded = await decodeWasm(nodeWasm, "avif", avif.outputs[0].bytes);
    expect([decoded.width, decoded.height]).toEqual([48, 64]);
    const jpg = await runClientTool("avif-a-jpg", [{ name: "foto.avif", bytes: avif.outputs[0].bytes }], { calidad: 90, fondo: "#FFFFFF" }, env());
    expect(sniffImage(jpg.outputs[0].bytes)).toBe("jpg");
    const back = await readImage(jpg.outputs[0].bytes);
    expect([back.width, back.height]).toEqual([48, 64]);
  });

  it("tiff-a-jpg: una imagen por página y ZIP, o solo la primera con aviso", async () => {
    const tiff = { name: "escaneo.tif", bytes: b64(TIFF_2P) };
    const all = await runClientTool("tiff-a-jpg", [tiff], { calidad: 90, fondo: "#FFFFFF", paginas: "todas" }, env());
    expect(all.outputs.map((o) => o.name)).toEqual(["escaneo-p1.jpg", "escaneo-p2.jpg", "imagenes-jpg.zip"]);
    const sizes = await Promise.all(all.outputs.slice(0, 2).map(async (o) => readImage(o.bytes)));
    expect(sizes.map((s) => [s.width, s.height])).toEqual([[30, 20], [16, 8]]);
    const second = sizes[1].data;
    expect(second[0]).toBeGreaterThan(180); // página roja
    expect(second[2]).toBeLessThan(80);
    const first = await runClientTool("tiff-a-jpg", [tiff], { calidad: 90, fondo: "#FFFFFF", paginas: "primera" }, env(undefined, { locale: "en" }));
    expect(first.outputs.map((o) => o.name)).toEqual(["escaneo.jpg"]);
    expect(first.notes).toEqual(["escaneo.tif: the TIFF has 2 pages; the first one was converted."]);
  });

  it("png-a-ico: tamaños elegidos, imagen centrada en un cuadrado transparente y aviso", async () => {
    const log: NodeCodecLog = { encodes: [] };
    const res = await runClientTool("png-a-ico", [PNG], { tamanos_ico: [48, 16, 256, 999], ajuste: "encajar" }, env(log));
    const ico = res.outputs[0];
    expect(ico.name).toBe("logo.ico");
    expect(ico.mime).toBe("image/x-icon");
    const dir = readIcoDirectory(ico.bytes);
    expect(dir.map((d) => [d.width, d.png])).toEqual([[16, false], [48, false], [256, true]]);
    expect(log.encodes[0]).toMatchObject({ width: 256, height: 256, fit: "contain", format: "png" });
    expect(res.notes).toEqual(["logo.png: no era cuadrada; se ha centrado con fondo transparente."]);
    // Fila superior del icono de 16 (40×30 encajado deja franjas arriba y abajo): transparente.
    const dib = dir[0].offset + 40;
    const topRowStored = dib + 15 * 16 * 4;
    expect(ico.bytes[topRowStored + 8 * 4 + 3]).toBe(0);
    await expect(runClientTool("png-a-ico", [PNG], { tamanos_ico: [999], ajuste: "encajar" }, env())).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });

  it("convertir-imagen a GIF, BMP con fondo y TIFF", async () => {
    const gif = await runClientTool("convertir-imagen", [PNG], { ...CONVERT, formato: "gif" }, env());
    expect(sniffImage(gif.outputs[0].bytes)).toBe("gif");
    const bmp = await runClientTool("convertir-imagen", [PNG], { ...CONVERT, formato: "bmp", fondo: "#00FF00" }, env());
    const b = bmp.outputs[0].bytes;
    expect(sniffImage(b)).toBe("bmp");
    // Último píxel de la primera fila guardada (abajo a la derecha, transparente): verde del fondo en BGR.
    const row = Math.ceil((40 * 3) / 4) * 4;
    expect(Array.from(b.subarray(54 + 39 * 3, 54 + 40 * 3))).toEqual([0, 255, 0]);
    expect(b.length).toBe(54 + row * 30);
    const tiff = await runClientTool("convertir-imagen", [PNG, JPG], { ...CONVERT, formato: "tiff" }, env());
    expect(tiff.outputs.map((o) => o.name)).toEqual(["logo.tiff", "foto.tiff", "imagenes-tiff.zip"]);
    expect(Object.keys(unzipSync(tiff.outputs[2].bytes))).toEqual(["logo.tiff", "foto.tiff"]);
    // El TIFF resultante se puede volver a convertir.
    const again = await runClientTool("convertir-imagen", [{ name: "logo.tiff", bytes: tiff.outputs[0].bytes }], { ...CONVERT, formato: "png" }, env());
    const img = await readImage(again.outputs[0].bytes);
    expect([img.width, img.height]).toEqual([40, 30]);
    await expect(runClientTool("convertir-imagen", [{ name: "x.png", bytes: new TextEncoder().encode("hola") }], { ...CONVERT, formato: "png" }, env()))
      .rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
  });
});

describe("svg-a-png y svg-a-jpg (A.10)", () => {
  const rect = '<rect width="40" height="20" fill="#0000FF" fill-opacity="0.5"/>';

  it("tamaño original, 2× y ancho personalizado manteniendo la proporción", async () => {
    const svg = { name: "dibujo.svg", bytes: SVG(rect) };
    for (const [o, size] of [[{ tamano: "original", ancho: 1000 }, [40, 20]], [{ tamano: "2x", ancho: 1000 }, [80, 40]], [{ tamano: "ancho", ancho: 1000 }, [1000, 500]]] as const) {
      const res = await runClientTool("svg-a-png", [svg], o, env());
      const img = await readImage(res.outputs[0].bytes);
      expect([img.width, img.height]).toEqual(size);
      expect(Array.from(img.data.subarray(0, 4))).toEqual([0, 0, 255, 128]);
    }
    await expect(runClientTool("svg-a-png", [svg], { tamano: "ancho", ancho: 20000 }, env())).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });

  it("JPG con fondo, calidad y texto con las fuentes Noto; avisa de las imágenes externas", async () => {
    const body = '<text x="2" y="16" font-family="Arial" font-size="16" fill="#000">Ñu</text><image href="https://ejemplo.test/a.png" width="5" height="5"/>';
    const log: NodeCodecLog = { encodes: [] };
    const res = await runClientTool("svg-a-jpg", [{ name: "texto.svg", bytes: SVG(body) }], { tamano: "2x", ancho: 1000, fondo: "#FFFF00", calidad: 70 }, env(log));
    expect(res.outputs[0].name).toBe("texto.jpg");
    expect(log.encodes[0]).toMatchObject({ format: "jpg", quality: 0.7, background: "#FFFF00" });
    const img = await readImage(res.outputs[0].bytes);
    expect([img.width, img.height]).toEqual([80, 40]);
    const corner = Array.from(img.data.subarray((39 * 80 + 79) * 4, (39 * 80 + 79) * 4 + 3));
    expect(corner[0]).toBeGreaterThan(230);
    expect(corner[2]).toBeLessThan(40);
    let ink = 0;
    for (let i = 0; i < img.data.length; i += 4) if (img.data[i] < 80 && img.data[i + 1] < 80) ink += 1;
    expect(ink).toBeGreaterThan(50);
    expect(res.notes).toEqual(["texto.svg: enlaza imágenes externas, que no se cargan (solo se pintan las incrustadas)."]);
  });

  it("rechaza lo que no es SVG y los SVG que no se pueden leer", async () => {
    await expect(runClientTool("svg-a-png", [PNG], { tamano: "original", ancho: 1000 }, env())).rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
    const broken = { name: "roto.svg", bytes: new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect') };
    await expect(runClientTool("svg-a-png", [broken], { tamano: "original", ancho: 1000 }, env())).rejects.toMatchObject({ code: "CORRUPT_FILE" });
  });
});

describe("crear-favicon", () => {
  const OPTIONS = { nombre: "Producto Demo", color_tema: "#112233", fondo: "#FF0000", margen: 10, ajuste: "encajar" };

  it("desde PNG: ICO, iconos de Apple y Android, maskable, manifiesto y código HTML", async () => {
    const res = await runClientTool("crear-favicon", [PNG], OPTIONS, env());
    expect(res.outputs.map((o) => o.name)).toEqual(["favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-mask.png",
      "manifest.webmanifest", "codigo-html.txt", "favicon.zip"]);
    const byName = Object.fromEntries(res.outputs.map((o) => [o.name, o.bytes]));
    expect(readIcoDirectory(byName["favicon.ico"]).map((d) => d.width)).toEqual([16, 32, 48]);
    const apple = await readImage(byName["apple-touch-icon.png"]);
    expect([apple.width, apple.height]).toEqual([180, 180]);
    expect(Array.from(apple.data.subarray(0, 4))).toEqual([255, 0, 0, 255]); // fondo opaco en el margen
    const mask = await readImage(byName["icon-mask.png"]);
    expect(Array.from(mask.data.subarray(0, 4))).toEqual([255, 0, 0, 255]);
    const icon = await readImage(byName["icon-512.png"]);
    expect([icon.width, icon.height, icon.data[3]]).toEqual([512, 512, 0]); // transparente fuera de la imagen
    const manifest = JSON.parse(new TextDecoder().decode(byName["manifest.webmanifest"]));
    expect(manifest).toMatchObject({ name: "Producto Demo", theme_color: "#112233" });
    expect(manifest.icons.map((i: { src: string }) => i.src)).toEqual(["/icon-192.png", "/icon-512.png", "/icon-mask.png"]);
    expect(res.display?.[0]).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png">');
    expect(res.display?.[0]).not.toContain("icon.svg");
    expect(Object.keys(unzipSync(byName["favicon.zip"]))).toHaveLength(7);
  });

  it("desde SVG incluye icon.svg y su etiqueta", async () => {
    const svg = { name: "marca.svg", bytes: SVG('<circle cx="20" cy="20" r="18" fill="#08f"/>', 40, 40) };
    const res = await runClientTool("crear-favicon", [svg], { ...OPTIONS, nombre: "" }, env());
    expect(res.outputs.map((o) => o.name)).toContain("icon.svg");
    expect(res.display?.[0]).toContain('<link rel="icon" href="/icon.svg" type="image/svg+xml">');
    const manifest = JSON.parse(new TextDecoder().decode(res.outputs.find((o) => o.name === "manifest.webmanifest")!.bytes));
    expect(manifest.name).toBe("marca");
    expect(res.notes).toEqual([]);
  });
});

describe("quitar-metadatos-foto e imagen-a-base64", () => {
  it("quita los metadatos con nota por archivo y rechaza otros formatos", async () => {
    const res = await runClientTool("quitar-metadatos-foto", [JPG, PNG], { que: "todo", conservar_orientacion: true }, env());
    expect(res.outputs.map((o) => o.name)).toEqual(["foto-sin-metadatos.jpg", "logo-sin-metadatos.png", "fotos-sin-metadatos.zip"]);
    expect(res.outputs[0].note).toBe("Quitado: EXIF, ubicación GPS, XMP, comentarios, datos añadidos tras la imagen (vídeo de Motion Photo, profundidad o miniaturas). "
      + "Se conserva la orientación para que la foto no salga girada.");
    const gps = await runClientTool("quitar-metadatos-foto", [JPG], { que: "solo_gps", conservar_orientacion: true }, env(undefined, { locale: "en" }));
    expect(gps.outputs[0].name).toBe("foto-sin-gps.jpg");
    expect(gps.outputs[0].note).toBe("GPS location removed; the rest of the metadata is kept.");
    const clean = await runClientTool("quitar-metadatos-foto", [{ name: "limpia.jpg", bytes: gps.outputs[0].bytes }], { que: "solo_gps", conservar_orientacion: true }, env());
    expect(clean.outputs[0].note).toBe("No tenía ubicación GPS.");
    await expect(runClientTool("quitar-metadatos-foto", [{ name: "a.tiff", bytes: b64(TIFF_2P) }], { que: "todo", conservar_orientacion: true }, env()))
      .rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
  });

  it("imagen-a-base64 en data URI, CSS y HTML; si es muy largo, solo en el TXT", async () => {
    const uri = await runClientTool("imagen-a-base64", [PNG], { formato: "data_uri" }, env());
    expect(uri.display?.[0].startsWith("data:image/png;base64,")).toBe(true);
    expect(Buffer.from(uri.display![0].split(",")[1], "base64").equals(Buffer.from(PNG.bytes))).toBe(true);
    expect(uri.outputs[0].name).toBe("logo-base64.txt");
    const css = await runClientTool("imagen-a-base64", [JPG], { formato: "css" }, env());
    expect(css.display?.[0]).toMatch(/^background-image: url\("data:image\/jpeg;base64,[^"]+"\);$/);
    const html = await runClientTool("imagen-a-base64", [{ name: "s.svg", bytes: SVG("") }], { formato: "html" }, env());
    expect(html.display?.[0]).toMatch(/^<img src="data:image\/svg\+xml;base64,[^"]+" alt="">$/);
    const big = new Uint8Array(200_000);
    big.set(PNG.bytes.subarray(0, 16));
    const long = await runClientTool("imagen-a-base64", [{ name: "grande.png", bytes: big }], { formato: "base64" }, env());
    expect(long.display).toEqual([]);
    expect(long.notes).toEqual(["grande.png: el texto es demasiado largo para mostrarlo aquí; descarga el TXT."]);
    expect(long.outputs[0].bytes.length).toBe(Math.ceil(200_000 / 3) * 4);
  });
});
