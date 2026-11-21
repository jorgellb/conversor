"use client";
// Modelos 3D en three.js (MIT) para visor-3d y render-modelo-3d (7.20, F7-H, D-257).
//
// - STL, OBJ (con su MTL y texturas si se eligen a la vez), 3MF, PLY, GLB/glTF y AMF con los cargadores de three.js.
//   El 3MF y el AMF usan DOMParser, que no existe en los Web Workers: se abren en el hilo principal.
// - Draco: el GLB se decodifica antes en el worker de las herramientas con glTF Transform y draco3d (D-257), y three.js
//   recibe un GLB sin Draco. Así no hace falta DRACOLoader, que crea sus propios workers desde blob: y pide el
//   decodificador por su cuenta. meshopt lo decodifica three.js con su propio decodificador.
// - Unidades: glTF va en metros y con Y vertical; STL, 3MF, AMF y PLY se suponen en milímetros y con Z vertical
//   (impresión 3D); OBJ, en milímetros y con Y vertical. El modelo se gira para que quede de pie en la escena (Y arriba).
// - Los archivos que el modelo enlaza (texturas, .bin) se buscan entre los elegidos, por su nombre; si no están, faltan.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

import { askWorker } from "@/lib/client-runner";

export const MODEL_EXTS = ["stl", "obj", "3mf", "ply", "glb", "gltf", "amf"] as const;
export type ModelExt = (typeof MODEL_EXTS)[number];
export const MAX_MODEL_BYTES = 512 * 1024 * 1024;

export interface LoadedModel {
  root: THREE.Group;
  ext: ModelExt;
  name: string;
  triangles: number;
  vertices: number;
  meshes: number;
  /** Puntos de una nube de puntos (PLY sin caras). */
  points: number;
  /** Milímetros por unidad del archivo (glTF: 1000). */
  mmPerUnit: number;
  up: "y" | "z";
  /** Avisos: texturas o archivos enlazados que faltan, KTX2 sin decodificar… */
  warnings: string[];
  dispose: () => void;
}

export class ModelError extends Error {
  constructor(readonly code: "UNSUPPORTED_FORMAT" | "CORRUPT_FILE" | "LIMIT_EXCEEDED" | "EMPTY" | "MISSING" | "KTX2" | "NO_WEBGL", detail = "") {
    super(detail || code);
  }
}

export function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

export function isModel(name: string): boolean {
  return (MODEL_EXTS as readonly string[]).includes(extOf(name));
}

/** Gris claro con algo de brillo para las mallas sin material (STL, PLY sin color). */
export function defaultMaterial(vertexColors = false): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: vertexColors ? 0xffffff : 0xb8bcc2, roughness: 0.55, metalness: 0.05, vertexColors,
    side: THREE.DoubleSide });
}

function meshOf(geometry: THREE.BufferGeometry): THREE.Mesh {
  if (!geometry.getAttribute("normal")) geometry.computeVertexNormals();
  const colors = Boolean(geometry.getAttribute("color"));
  return new THREE.Mesh(geometry, defaultMaterial(colors));
}

/** `data:[tipo][;base64],datos` a bytes (sin fetch: la CSP no deja leer `data:` con connect-src). */
export function dataUriBytes(uri: string): { bytes: Uint8Array; type: string } | null {
  const m = /^data:([^,;]*)((?:;[^,;]*)*?)(;base64)?,(.*)$/s.exec(uri);
  if (!m) return null;
  if (m[3]) {
    const bin = atob(m[4].replace(/\s+/g, ""));
    const bytes = new Uint8Array(bin.length);
    for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
    return { bytes, type: m[1] || "application/octet-stream" };
  }
  return { bytes: new TextEncoder().encode(decodeURIComponent(m[4])), type: m[1] || "text/plain" };
}

/**
 * Rutas enlazadas por el modelo → URL blob: de los archivos elegidos con el mismo nombre (sin carpetas ni mayúsculas).
 * Los `data:` incrustados pasan también a blob: (D-260: three.js los pedía con fetch y la CSP los bloqueaba). Lo que
 * falta se apunta en `missing` y se sirve vacío; si era imprescindible (el .bin), la carga falla con ese aviso.
 */
function linkedFiles(files: File[], warnings: string[], missingText: (name: string) => string): {
  manager: THREE.LoadingManager; revoke: () => void; missing: Set<string>;
} {
  const byName = new Map(files.map((f) => [f.name.toLowerCase(), f]));
  const urls: string[] = [];
  const missing = new Set<string>();
  const manager = new THREE.LoadingManager();
  const blobUrl = (blob: Blob) => {
    const url = URL.createObjectURL(blob);
    urls.push(url);
    return url;
  };
  manager.setURLModifier((url) => {
    if (url.startsWith("blob:")) return url;
    if (url.startsWith("data:")) {
      const data = dataUriBytes(url);
      return blobUrl(data ? new Blob([new Uint8Array(data.bytes)], { type: data.type }) : new Blob());
    }
    const base = decodeURIComponent(url.split(/[?#]/)[0]).split(/[\\/]/).pop()!.toLowerCase();
    const file = byName.get(base);
    if (!file) {
      if (!missing.has(base)) {
        missing.add(base);
        warnings.push(missingText(base));
      }
      return blobUrl(new Blob());
    }
    return blobUrl(file);
  });
  return { manager, revoke: () => urls.forEach((u) => URL.revokeObjectURL(u)), missing };
}

/** Milímetros por unidad del 3MF (`unit` del modelo, que el cargador de three.js lee pero no aplica). */
async function threeMfUnit(buffer: ArrayBuffer): Promise<number> {
  const { unzipSync } = await import("three/examples/jsm/libs/fflate.module.js");
  try {
    const files = unzipSync(new Uint8Array(buffer), { filter: (f) => /^3d\/[^/]+\.model$/i.test(f.name) });
    const xml = Object.values(files)[0];
    const head = xml ? new TextDecoder().decode(xml.subarray(0, 4096)) : "";
    const unit = /<model[^>]*\bunit="([a-z]+)"/i.exec(head)?.[1]?.toLowerCase() ?? "millimeter";
    return { micron: 0.001, millimeter: 1, centimeter: 10, inch: 25.4, foot: 304.8, meter: 1000 }[unit] ?? 1;
  } catch {
    return 1;
  }
}

function gltfExtensions(bytes: Uint8Array): string[] {
  try {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint32(0, true) === 0x46546c67) {
      const length = view.getUint32(12, true);
      return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + length))).extensionsUsed ?? [];
    }
    return JSON.parse(new TextDecoder().decode(bytes)).extensionsUsed ?? [];
  } catch {
    throw new ModelError("CORRUPT_FILE");
  }
}

function countGeometry(root: THREE.Object3D): { triangles: number; vertices: number; meshes: number; points: number } {
  let triangles = 0, vertices = 0, meshes = 0, points = 0;
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if ((o as THREE.Points).isPoints) {
      meshes += 1;
      points += (o as THREE.Points).geometry.getAttribute("position")?.count ?? 0;
      return;
    }
    if (!mesh.isMesh) return;
    meshes += 1;
    const g = mesh.geometry;
    const count = g.getAttribute("position")?.count ?? 0;
    vertices += count;
    triangles += g.index ? g.index.count / 3 : count / 3;
  });
  return { triangles: Math.round(triangles), vertices, meshes, points };
}

export function disposeObject(root: THREE.Object3D): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh && !(o as THREE.LineSegments).isLineSegments && !(o as THREE.Points).isPoints) return;
    const original = (mesh.userData as { original?: THREE.Material | THREE.Material[] }).original;
    if (original) (Array.isArray(original) ? original : [original]).forEach((m) => m.dispose());
    mesh.geometry?.dispose();
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (!m) continue;
      for (const value of Object.values(m)) if (value instanceof THREE.Texture) value.dispose();
      m.dispose();
    }
  });
}

export interface LoadTexts {
  missing: (name: string) => string;
  ktx2: string;
}

/**
 * Abre el modelo principal (`main`) con los demás archivos elegidos como posibles recursos enlazados. `up` fuerza el eje
 * vertical («auto», según el formato).
 */
export async function loadModel(main: File, others: File[], texts: LoadTexts, up: "auto" | "y" | "z" = "auto"): Promise<LoadedModel> {
  const ext = extOf(main.name) as ModelExt;
  if (!(MODEL_EXTS as readonly string[]).includes(ext)) throw new ModelError("UNSUPPORTED_FORMAT");
  if (main.size > MAX_MODEL_BYTES) throw new ModelError("LIMIT_EXCEEDED");
  const warnings: string[] = [];
  const { manager, revoke, missing } = linkedFiles(others, warnings, texts.missing);
  const content = new THREE.Group();
  let mmPerUnit = 1;
  let fileUp: "y" | "z" = "z";
  try {
    const buffer = await main.arrayBuffer();
    switch (ext) {
      case "stl": {
        const { STLLoader } = await import("three/examples/jsm/loaders/STLLoader.js");
        content.add(meshOf(new STLLoader().parse(buffer)));
        break;
      }
      case "ply": {
        const { PLYLoader } = await import("three/examples/jsm/loaders/PLYLoader.js");
        const geometry = new PLYLoader().parse(buffer);
        if (!geometry.getAttribute("position")?.count) throw new ModelError("EMPTY");
        if (!geometry.index) {
          // Sin caras: es una nube de puntos (un escaneo), no una malla (D-260).
          const colors = Boolean(geometry.getAttribute("color"));
          geometry.computeBoundingSphere();
          const size = Math.max((geometry.boundingSphere?.radius ?? 1) / 400, 0.01);
          content.add(new THREE.Points(geometry, new THREE.PointsMaterial({ size, vertexColors: colors, color: colors ? 0xffffff : 0x6b7280 })));
          break;
        }
        content.add(meshOf(geometry));
        break;
      }
      case "obj": {
        const [{ OBJLoader }, { MTLLoader }] = await Promise.all([
          import("three/examples/jsm/loaders/OBJLoader.js"), import("three/examples/jsm/loaders/MTLLoader.js")]);
        const loader = new OBJLoader(manager);
        const text = new TextDecoder().decode(buffer);
        const mtlName = /^mtllib\s+(.+)$/m.exec(text)?.[1]?.trim();
        const mtl = mtlName ? others.find((f) => f.name.toLowerCase() === mtlName.split(/[\\/]/).pop()!.toLowerCase()) : undefined;
        if (mtl) {
          const materials = new MTLLoader(manager).parse(await mtl.text(), "");
          materials.preload();
          loader.setMaterials(materials);
        } else if (mtlName) warnings.push(texts.missing(mtlName));
        const group = loader.parse(text);
        if (!mtl) group.traverse((o) => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).material = defaultMaterial(); });
        content.add(group);
        fileUp = "y";
        break;
      }
      case "3mf": {
        const { ThreeMFLoader } = await import("three/examples/jsm/loaders/3MFLoader.js");
        content.add(new ThreeMFLoader(manager).parse(buffer));
        mmPerUnit = await threeMfUnit(buffer);
        break;
      }
      case "amf": {
        const { AMFLoader } = await import("three/examples/jsm/loaders/AMFLoader.js");
        content.add(new AMFLoader(manager).parse(buffer));
        break;
      }
      case "glb":
      case "gltf": {
        let bytes = new Uint8Array(buffer);
        const extensions = gltfExtensions(bytes);
        if (extensions.includes("KHR_texture_basisu")) warnings.push(texts.ktx2);
        if (extensions.includes("KHR_draco_mesh_compression")) {
          const plain = await askWorker<{ bytes: Uint8Array }>("__glb_plain", main);
          bytes = new Uint8Array(plain.bytes);
        }
        const loader = new GLTFLoader(manager).setMeshoptDecoder(MeshoptDecoder);
        const data = ext === "glb" || bytes[0] !== 0x7b ? bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) : new TextDecoder().decode(bytes);
        const gltf = await new Promise<{ scene: THREE.Group }>((resolve, reject) => loader.parse(data as ArrayBuffer, "", resolve as never, reject))
          .catch((err) => {
            // KTX2 obligatorio sin su decodificador (Basis no se incluye en la web): se dice, no «dañado» (D-260).
            if (/ktx2|basisu/i.test(String((err as Error)?.message ?? err))) throw new ModelError("KTX2");
            throw err;
          });
        content.add(gltf.scene);
        mmPerUnit = 1000;
        fileUp = "y";
        break;
      }
    }
  } catch (err) {
    revoke();
    if (err instanceof ModelError) throw err;
    if (missing.size) throw new ModelError("MISSING", [...missing].join(", "));
    throw new ModelError("CORRUPT_FILE", String((err as Error)?.message ?? err).slice(0, 200));
  }
  // Las texturas enlazadas se cargan después; las URL blob: se sueltan cuando el gestor termina.
  manager.onLoad = revoke;
  setTimeout(revoke, 60_000);
  const counts = countGeometry(content);
  if (!counts.meshes || (!counts.triangles && !counts.points)) {
    disposeObject(content);
    throw new ModelError("EMPTY");
  }
  const finalUp = up === "auto" ? fileUp : up;
  const root = new THREE.Group();
  root.name = main.name;
  content.scale.setScalar(mmPerUnit); // la escena trabaja en milímetros
  if (finalUp === "z") content.rotation.x = -Math.PI / 2;
  root.add(content);
  root.updateMatrixWorld(true);
  return {
    root, ext, name: main.name, ...counts, mmPerUnit, up: finalUp, warnings,
    dispose: () => disposeObject(root),
  };
}

/** Caja del modelo en milímetros, ya girado. */
export function boundsOf(root: THREE.Object3D): THREE.Box3 {
  root.updateMatrixWorld(true);
  return new THREE.Box3().setFromObject(root, true);
}

/** Apoya el modelo sobre el plano y lo centra en X y Z (la escena es Y arriba). */
export function placeOnFloor(root: THREE.Object3D): THREE.Box3 {
  const box = boundsOf(root);
  const center = box.getCenter(new THREE.Vector3());
  root.position.x -= center.x;
  root.position.z -= center.z;
  root.position.y -= box.min.y;
  return boundsOf(root);
}

export type ViewAngle = "isometrico" | "frontal" | "superior" | "lateral";

/** Coloca la cámara para que el modelo llene el encuadre desde el ángulo pedido (`margin` 1 = justo). */
export function frameCamera(camera: THREE.PerspectiveCamera, box: THREE.Box3, angle: ViewAngle, margin = 1.15): THREE.Vector3 {
  const center = box.getCenter(new THREE.Vector3());
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const dir = {
    isometrico: new THREE.Vector3(1, 0.8, 1),
    frontal: new THREE.Vector3(0, 0.08, 1),
    superior: new THREE.Vector3(0, 1, 0.0001),
    lateral: new THREE.Vector3(1, 0.08, 0),
  }[angle].normalize();
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * camera.aspect));
  const distance = (Math.max(sphere.radius, 1e-3) * margin) / Math.sin(fit / 2);
  camera.position.copy(center).addScaledVector(dir, distance);
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = distance * 100;
  camera.up.set(0, 1, 0);
  camera.lookAt(center);
  camera.updateProjectionMatrix();
  return center;
}

/** Mapa de entorno de estudio generado en el navegador (sin descargar nada): sin él, los materiales metálicos de glTF salen
 * casi negros (D-260). */
export async function addEnvironment(scene: THREE.Scene, renderer: THREE.WebGLRenderer): Promise<void> {
  const { RoomEnvironment } = await import("three/examples/jsm/environments/RoomEnvironment.js");
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.6;
  pmrem.dispose();
}

/** Luces de estudio: ambiente, hemisférica y dos direccionales. */
export function addLights(scene: THREE.Scene): void {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 1.4));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(1, 2, 1.5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.8);
  fill.position.set(-1.5, 0.5, -1);
  scene.add(fill);
}

/** Cambia el color de todas las mallas (o lo devuelve al original con `null`), guardando los materiales originales. */
export function overrideColor(root: THREE.Object3D, color: string | null): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh & { userData: { original?: THREE.Material | THREE.Material[] } };
    if (!mesh.isMesh) return;
    if (color === null) {
      if (mesh.userData.original) {
        (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach((m) => m.dispose());
        mesh.material = mesh.userData.original;
        delete mesh.userData.original;
      }
      return;
    }
    mesh.userData.original ??= mesh.material;
    const material = defaultMaterial();
    material.color.set(color);
    if (mesh.material !== mesh.userData.original) (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach((m) => m.dispose());
    mesh.material = material;
  });
}

/** Aplica a todos los materiales del modelo (alambre, planos de corte…). */
export function eachMaterial(root: THREE.Object3D, fn: (m: THREE.Material) => void): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) fn(m);
  });
}

/** PNG del lienzo de un renderizador (con preserveDrawingBuffer o justo después de pintar). */
export function canvasPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("png"))), "image/png"));
}

export function formatMm(value: number, locale: string): string {
  const digits = value >= 100 ? 1 : 2;
  return `${value.toLocaleString(locale, { maximumFractionDigits: digits })} mm`;
}
