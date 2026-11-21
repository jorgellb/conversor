/// <reference path="./draco3d.d.ts" />
// comprimir-glb (7.20, F7-H, D-257): glTF Transform (MIT) con Draco (draco3d, Apache-2.0) o meshopt (meshoptimizer, MIT)
// en el Web Worker; el archivo no sale del navegador.
//
// - Se aceptan GLB y glTF con todo dentro (búferes e imágenes en `data:`); un glTF que enlaza archivos de fuera no se
//   puede abrir solo y se avisa.
// - Siempre: deduplicar accesores, mallas, materiales y texturas, quitar lo que nadie usa y (si se pide) soldar los
//   vértices idénticos. Después, Draco con los bits de cuantización de la calidad elegida o meshopt.
// - Texturas: se pueden reducir a un tamaño máximo y pasar a WebP (EXT_texture_webp); cada una solo se cambia si queda
//   más pequeña.
// - Nunca se devuelve un archivo mayor que el original: si no se gana nada, se dice y se devuelve el de entrada.
// - También sirve para quitar la compresión (`metodo: ninguno`), para programas que no leen Draco ni meshopt.
import { Document, WebIO, type Texture } from "@gltf-transform/core";
import { ALL_EXTENSIONS, EXTTextureWebP } from "@gltf-transform/extensions";
import { dedup, draco, meshopt, prune, weld } from "@gltf-transform/functions";

import { stem, withBatchZip, type InFile, type OutFile, type Progress, type ToolResult } from "./common";
import type { ImageCodec } from "./imagetools";
import type { Locale } from "./notes";
import { ToolError } from "./tool-error";
import { encodeWebp, type WasmLoader } from "./wasmcodecs";

export interface ComprimirGlbOptions {
  metodo?: "draco" | "meshopt" | "ninguno";
  calidad?: "alta" | "media" | "baja";
  soldar?: boolean;
  texturas?: "conservar" | "webp";
  tamano_textura?: 0 | 512 | 1024 | 2048 | 4096;
  calidad_textura?: number;
}

export interface GlbEnv {
  wasm?: WasmLoader;
  codec?: ImageCodec;
  progress?: Progress;
  locale?: Locale;
}

/** Bits de cuantización de Draco por calidad (posición, normal, coordenadas de textura, color, genéricos). */
export const DRACO_BITS = {
  alta: { quantizePosition: 14, quantizeNormal: 10, quantizeTexcoord: 12, quantizeColor: 8, quantizeGeneric: 12 },
  media: { quantizePosition: 12, quantizeNormal: 8, quantizeTexcoord: 10, quantizeColor: 8, quantizeGeneric: 10 },
  baja: { quantizePosition: 11, quantizeNormal: 7, quantizeTexcoord: 9, quantizeColor: 7, quantizeGeneric: 8 },
} as const;
const MESHOPT_LEVEL = { alta: "medium", media: "medium", baja: "high" } as const;

const MAX_INPUT = 512 * 1024 * 1024;
const GLB_MAGIC = 0x46546c67; // «glTF»
const GLB_MIME = "model/gltf-binary";

const TEXTS = {
  es: {
    result: (a: string, b: string, pct: number) => `De ${a} a ${b} (${pct} % menos).`,
    noGain: "Ya estaba tan comprimido como se puede con estas opciones: se devuelve el original sin cambios.",
    textures: (n: number) => `${n} ${n === 1 ? "textura pasada" : "texturas pasadas"} a WebP o reducidas.`,
    draco: "Comprimido con Draco: lo leen three.js, Babylon.js, Blender, model-viewer y la mayoría de visores web.",
    meshopt: "Comprimido con meshopt: lo leen three.js, Babylon.js y model-viewer; Blender lo abre desde la versión 3.4 con un complemento.",
    plain: "Sin compresión de mallas: lo abre cualquier programa que lea glTF.",
  },
  en: {
    result: (a: string, b: string, pct: number) => `From ${a} to ${b} (${pct}% smaller).`,
    noGain: "It was already as compressed as these options allow: the original is returned unchanged.",
    textures: (n: number) => `${n} ${n === 1 ? "texture" : "textures"} converted to WebP or reduced.`,
    draco: "Compressed with Draco: read by three.js, Babylon.js, Blender, model-viewer and most web viewers.",
    meshopt: "Compressed with meshopt: read by three.js, Babylon.js and model-viewer; Blender opens it from 3.4 with an add-on.",
    plain: "No mesh compression: any program that reads glTF opens it.",
  },
};

export function humanSize(bytes: number, locale: Locale = "es"): string {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const text = unit === 0 ? String(value) : value.toFixed(value < 10 ? 1 : 0);
  return `${locale === "es" ? text.replace(".", ",") : text} ${units[unit]}`;
}

// ——— Draco en WebAssembly: el .wasm lo entrega quien llama (el worker lo descarga de /codecs/) ———

type DracoFactory = (opts: object) => Promise<unknown>;
const dracoModules = new Map<string, Promise<unknown>>();

function dracoModule(load: WasmLoader, kind: "draco_encoder" | "draco_decoder"): Promise<unknown> {
  let p = dracoModules.get(kind);
  if (!p) {
    p = (async () => {
      const [glue, wasm] = await Promise.all([
        kind === "draco_encoder" ? import("draco3d/draco_encoder_nodejs.js") : import("draco3d/draco_decoder_nodejs.js"),
        load(kind),
      ]);
      const factory = ((glue as { default?: unknown }).default ?? glue) as DracoFactory;
      return factory({
        instantiateWasm(imports: WebAssembly.Imports, done: (instance: WebAssembly.Instance) => void) {
          const instance = new WebAssembly.Instance(wasm, imports);
          done(instance);
          return instance.exports;
        },
      });
    })();
    p.catch(() => dracoModules.delete(kind));
    dracoModules.set(kind, p);
  }
  return p;
}

async function meshoptCodecs() {
  const { MeshoptDecoder, MeshoptEncoder } = await import("meshoptimizer");
  await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
  return { MeshoptDecoder, MeshoptEncoder };
}

/** Lector y escritor de glTF con todas las extensiones de Khronos y los códecs que hagan falta. */
export async function gltfIO(load: WasmLoader | undefined, needs: { encoder?: boolean; decoder?: boolean }): Promise<WebIO> {
  const io = new WebIO().registerExtensions(ALL_EXTENSIONS);
  const deps: Record<string, unknown> = {};
  const meshopts = await meshoptCodecs();
  deps["meshopt.decoder"] = meshopts.MeshoptDecoder;
  deps["meshopt.encoder"] = meshopts.MeshoptEncoder;
  if (load && needs.decoder) deps["draco3d.decoder"] = await dracoModule(load, "draco_decoder");
  if (load && needs.encoder) deps["draco3d.encoder"] = await dracoModule(load, "draco_encoder");
  io.registerDependencies(deps);
  return io;
}

function isGlb(bytes: Uint8Array): boolean {
  return bytes.length >= 12 && new DataView(bytes.buffer, bytes.byteOffset, 12).getUint32(0, true) === GLB_MAGIC;
}

/** Extensiones de un GLB o glTF sin decodificarlo (para saber si hace falta el decodificador de Draco). */
export function gltfJson(bytes: Uint8Array): { extensionsUsed?: string[]; buffers?: { uri?: string }[]; images?: { uri?: string }[] } {
  try {
    if (isGlb(bytes)) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const length = view.getUint32(12, true);
      if (view.getUint32(16, true) !== 0x4e4f534a || 20 + length > bytes.length) throw new Error("json");
      return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + length)));
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new ToolError("CORRUPT_FILE", "glTF ilegible");
  }
}

/** Abre un GLB, o un glTF con todo incrustado, en un documento de glTF Transform. */
export async function readGltf(io: WebIO, file: InFile): Promise<Document> {
  if (file.bytes.length > MAX_INPUT) throw new ToolError("LIMIT_EXCEEDED", "glb_too_big");
  const json = gltfJson(file.bytes);
  const external = [...(json.buffers ?? []), ...(json.images ?? [])].some((r) => r.uri && !r.uri.startsWith("data:"));
  if (!isGlb(file.bytes) && external) throw new ToolError("UNSUPPORTED_FORMAT", "gltf_external");
  try {
    if (isGlb(file.bytes)) return await io.readBinary(file.bytes);
    return await io.readJSON({ json: json as never, resources: {} });
  } catch (err) {
    if (err instanceof ToolError) throw err;
    throw new ToolError("CORRUPT_FILE", `glTF ilegible: ${String((err as Error)?.message ?? err).slice(0, 200)}`);
  }
}

/** Textura a WebP (y como mucho `maxSide` px por lado); solo si queda más pequeña. */
async function textureToWebp(texture: Texture, env: GlbEnv, maxSide: number, quality: number, toWebp: boolean): Promise<boolean> {
  const image = texture.getImage();
  const mime = texture.getMimeType();
  if (!image || !env.codec?.rgba) return false;
  if (!toWebp && !maxSide) return false;
  const decoded = await env.codec.decode({ name: `textura.${mime.split("/")[1] ?? "png"}`, bytes: image });
  try {
    const side = Math.max(decoded.width, decoded.height);
    const scale = maxSide && side > maxSide ? maxSide / side : 1;
    if (scale === 1 && (!toWebp || mime === "image/webp")) return false;
    const width = Math.max(1, Math.round(decoded.width * scale));
    const height = Math.max(1, Math.round(decoded.height * scale));
    let bytes: Uint8Array;
    let outMime = mime;
    if (toWebp || mime === "image/webp") {
      bytes = await encodeWebp(env.wasm!, await env.codec.rgba(decoded, { width, height }), { quality, lossless: false });
      outMime = "image/webp";
    } else {
      const format = mime === "image/jpeg" ? "jpg" : "png";
      bytes = await env.codec.encode(decoded, { width, height, format, quality: quality / 100 });
    }
    if (bytes.length >= image.length && scale === 1) return false;
    texture.setImage(bytes).setMimeType(outMime);
    if (outMime === "image/webp" && texture.getURI()) texture.setURI(texture.getURI().replace(/\.(png|jpe?g)$/i, ".webp"));
    return true;
  } finally {
    env.codec.close?.(decoded);
  }
}

async function compressOne(file: InFile, o: ComprimirGlbOptions, env: GlbEnv): Promise<OutFile> {
  const t = TEXTS[env.locale === "en" ? "en" : "es"];
  const method = o.metodo ?? "draco";
  const quality = o.calidad ?? "alta";
  const usesDraco = (gltfJson(file.bytes).extensionsUsed ?? []).includes("KHR_draco_mesh_compression");
  if ((method === "draco" || usesDraco) && !env.wasm) throw new ToolError("INTERNAL", "Falta WebAssembly");
  const io = await gltfIO(env.wasm, { encoder: method === "draco", decoder: usesDraco });
  const doc = await readGltf(io, file);
  const root = doc.getRoot();
  // Se quitan las compresiones de entrada: la salida solo lleva la elegida.
  for (const ext of root.listExtensionsUsed()) {
    if (ext.extensionName === "KHR_draco_mesh_compression" || ext.extensionName === "EXT_meshopt_compression") ext.dispose();
  }
  const transforms = [dedup(), prune({ keepAttributes: false, keepLeaves: false })];
  if (o.soldar ?? true) transforms.push(weld());
  await doc.transform(...transforms);
  let changedTextures = 0;
  const toWebp = (o.texturas ?? "conservar") === "webp";
  const maxSide = Number(o.tamano_textura ?? 0);
  if ((toWebp || maxSide) && env.codec && env.wasm) {
    const textures = root.listTextures();
    for (const [i, texture] of textures.entries()) {
      if (await textureToWebp(texture, env, maxSide, Math.min(100, Math.max(1, Number(o.calidad_textura ?? 85))), toWebp)) changedTextures += 1;
      env.progress?.(0.2 + (0.4 * (i + 1)) / Math.max(1, textures.length));
    }
    if (root.listTextures().some((tx) => tx.getMimeType() === "image/webp")) doc.createExtension(EXTTextureWebP).setRequired(true);
  }
  env.progress?.(0.65);
  if (method === "draco") await doc.transform(draco({ method: "edgebreaker", ...DRACO_BITS[quality] }));
  else if (method === "meshopt") {
    const { MeshoptEncoder } = await meshoptCodecs();
    await doc.transform(meshopt({ encoder: MeshoptEncoder, level: MESHOPT_LEVEL[quality] }));
  }
  const bytes = await io.writeBinary(doc);
  env.progress?.(0.95);
  const name = `${stem(file.name)}.glb`;
  const notes = [method === "draco" ? t.draco : method === "meshopt" ? t.meshopt : t.plain];
  if (changedTextures) notes.push(t.textures(changedTextures));
  // Quitar la compresión (ninguno) puede agrandar el archivo a propósito; en los otros casos, nunca se devuelve uno mayor.
  if (method !== "ninguno" && bytes.length >= file.bytes.length && isGlb(file.bytes)) {
    return { name, bytes: file.bytes, mime: GLB_MIME, note: t.noGain };
  }
  const pct = Math.round((1 - bytes.length / file.bytes.length) * 100);
  if (pct > 0) notes.unshift(t.result(humanSize(file.bytes.length, env.locale), humanSize(bytes.length, env.locale), pct));
  return { name, bytes, mime: GLB_MIME, note: notes.join(" ") };
}

export async function comprimirGlb(files: InFile[], o: ComprimirGlbOptions, env: GlbEnv): Promise<ToolResult> {
  if (!files.length) throw new ToolError("INVALID_OPTIONS", "Sin archivos");
  const outputs: OutFile[] = [];
  for (const [i, file] of files.entries()) {
    const step = (f: number) => env.progress?.((i + f) / files.length);
    outputs.push(await compressOne(file, o, { ...env, progress: step }));
  }
  return { outputs: withBatchZip(outputs, "modelos-glb.zip"), notes: [] };
}

/** Para el visor: el GLB sin Draco (three.js lo abre sin su decodificador ni workers de blob:). */
export async function glbSinDraco(file: InFile, load: WasmLoader): Promise<Uint8Array> {
  const io = await gltfIO(load, { decoder: true });
  const doc = await readGltf(io, file);
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (ext.extensionName === "KHR_draco_mesh_compression") ext.dispose();
  }
  return io.writeBinary(doc);
}
