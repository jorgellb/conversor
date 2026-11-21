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
  /** Milímetros por unidad del archivo (glTF: 1000). */
  mmPerUnit: number;
  up: "y" | "z";
  /** Avisos: texturas o archivos enlazados que faltan, KTX2 sin decodificar… */
  warnings: string[];
  dispose: () => void;
}

export class ModelError extends Error {
  constructor(readonly code: "UNSUPPORTED_FORMAT" | "CORRUPT_FILE" | "LIMIT_EXCEEDED" | "EMPTY", detail = "") {
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

/** Rutas enlazadas por el modelo → URL blob: de los archivos elegidos con el mismo nombre (sin carpetas ni mayúsculas). */
function linkedFiles(files: File[], warnings: string[], missingText: (name: string) => string): { manager: THREE.LoadingManager; revoke: () => void } {
  const byName = new Map(files.map((f) => [f.name.toLowerCase(), f]));
  const urls: string[] = [];
  const missing = new Set<string>();
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => {
    if (url.startsWith("data:") || url.startsWith("blob:")) return url;
    const base = decodeURIComponent(url.split(/[?#]/)[0]).split(/[\\/]/).pop()!.toLowerCase();
    const file = byName.get(base);
    if (!file) {
      if (!missing.has(base)) {
        missing.add(base);
        warnings.push(missingText(base));
      }
      return "data:,";
    }
    const blob = URL.createObjectURL(file);
    urls.push(blob);
    return blob;
  });
  return { manager, revoke: () => urls.forEach((u) => URL.revokeObjectURL(u)) };
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

function countGeometry(root: THREE.Object3D): { triangles: number; vertices: number; meshes: number } {
  let triangles = 0, vertices = 0, meshes = 0;
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    meshes += 1;
    const g = mesh.geometry;
    const count = g.getAttribute("position")?.count ?? 0;
    vertices += count;
    triangles += g.index ? g.index.count / 3 : count / 3;
  });
  return { triangles: Math.round(triangles), vertices, meshes };
}

export function disposeObject(root: THREE.Object3D): void {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh && !(o as THREE.LineSegments).isLineSegments) return;
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
  const { manager, revoke } = linkedFiles(others, warnings, texts.missing);
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
        if (!geometry.index && !geometry.getAttribute("position")?.count) throw new ModelError("EMPTY");
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
        const gltf = await new Promise<{ scene: THREE.Group }>((resolve, reject) => loader.parse(data as ArrayBuffer, "", resolve as never, reject));
        content.add(gltf.scene);
        mmPerUnit = 1000;
        fileUp = "y";
        break;
      }
    }
  } catch (err) {
    revoke();
    if (err instanceof ModelError) throw err;
    throw new ModelError("CORRUPT_FILE", String((err as Error)?.message ?? err).slice(0, 200));
  }
  // Las texturas enlazadas se cargan después; las URL blob: se sueltan cuando el gestor termina.
  manager.onLoad = revoke;
  setTimeout(revoke, 60_000);
  const counts = countGeometry(content);
  if (!counts.meshes || !counts.triangles) {
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

/** Luces de estudio: ambiente, hemisférica y dos direccionales (no hace falta mapa de entorno). */
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
