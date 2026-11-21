// comprimir-glb (D-257): Draco y meshopt con glTF Transform, texturas a WebP y nunca un archivo mayor.
import { Document, WebIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import { MeshoptDecoder } from "meshoptimizer";
import { describe, expect, it } from "vitest";

import { DRACO_BITS, glbSinDraco } from "../src/glb";
import { runClientTool, type ClientEnv } from "../src/index";
import { encodePng } from "../src/wasmcodecs";
import { nodeCodec } from "./image-node";
import { nodeWasm } from "./wasm-node";

const env: ClientEnv = { wasm: nodeWasm, codec: nodeCodec(), locale: "es" };

/** Esfera UV de `n` × `n` con normales, coordenadas de textura y, si se pide, una textura PNG de 512 px. */
async function sphereGlb(n = 120, texture = false): Promise<Uint8Array> {
  const doc = new Document();
  const buffer = doc.createBuffer();
  const pos: number[] = [];
  const nor: number[] = [];
  const uv: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    for (let j = 0; j <= n; j++) {
      const th = (i / n) * Math.PI;
      const ph = (j / n) * 2 * Math.PI;
      const x = Math.sin(th) * Math.cos(ph), y = Math.cos(th), z = Math.sin(th) * Math.sin(ph);
      pos.push(x * 0.05, y * 0.05, z * 0.05);
      nor.push(x, y, z);
      uv.push(j / n, i / n);
    }
  }
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const a = i * (n + 1) + j, b = a + n + 1;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const prim = doc.createPrimitive()
    .setAttribute("POSITION", doc.createAccessor().setType("VEC3").setArray(new Float32Array(pos)).setBuffer(buffer))
    .setAttribute("NORMAL", doc.createAccessor().setType("VEC3").setArray(new Float32Array(nor)).setBuffer(buffer))
    .setAttribute("TEXCOORD_0", doc.createAccessor().setType("VEC2").setArray(new Float32Array(uv)).setBuffer(buffer))
    .setIndices(doc.createAccessor().setType("SCALAR").setArray(new Uint32Array(idx)).setBuffer(buffer));
  const material = doc.createMaterial("piel").setBaseColorFactor([0.8, 0.3, 0.2, 1]);
  if (texture) {
    const size = 512;
    const data = new Uint8ClampedArray(size * size * 4);
    for (let k = 0; k < size * size; k++) {
      const x = k % size, y = Math.floor(k / size);
      data.set([(x * 7) & 255, (y * 3) & 255, ((x ^ y) * 5) & 255, 255], k * 4);
    }
    const png = await encodePng(nodeWasm, { data, width: size, height: size });
    material.setBaseColorTexture(doc.createTexture("color").setImage(png).setMimeType("image/png"));
  }
  prim.setMaterial(material);
  doc.createScene().addChild(doc.createNode("bola").setMesh(doc.createMesh("bola").addPrimitive(prim)));
  return new WebIO().writeBinary(doc);
}

async function read(bytes: Uint8Array): Promise<Document> {
  const io = new WebIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ "meshopt.decoder": MeshoptDecoder });
  await MeshoptDecoder.ready;
  return io.readBinary(bytes);
}

function jsonOf(glb: Uint8Array): { extensionsUsed?: string[]; extensionsRequired?: string[]; images?: { mimeType?: string }[] } {
  const view = new DataView(glb.buffer, glb.byteOffset, glb.byteLength);
  return JSON.parse(new TextDecoder().decode(glb.subarray(20, 20 + view.getUint32(12, true))));
}

describe("comprimir-glb", () => {
  it("comprime con Draco y se vuelve a abrir con la misma geometría", async () => {
    const input = await sphereGlb();
    const result = await runClientTool("comprimir-glb", [{ name: "bola.glb", bytes: input }], { metodo: "draco", calidad: "alta" }, env);
    const out = result.outputs[0];
    expect(out.name).toBe("bola.glb");
    expect(out.bytes.length).toBeLessThan(input.length * 0.4);
    expect(jsonOf(out.bytes).extensionsRequired).toContain("KHR_draco_mesh_compression");
    expect(out.note).toMatch(/menos/);
    // Se vuelve a abrir decodificando Draco: mismos triángulos y posiciones dentro del error de 14 bits.
    const plain = await glbSinDraco({ name: "bola.glb", bytes: out.bytes }, nodeWasm);
    const prim = (await read(plain)).getRoot().listMeshes()[0].listPrimitives()[0];
    // Draco quita los triángulos degenerados (los de los polos de la esfera): el resto se conserva.
    expect(prim.getIndices()!.getCount()).toBeGreaterThan(120 * 120 * 6 * 0.98);
    const [min, max] = [prim.getAttribute("POSITION")!.getMin([]), prim.getAttribute("POSITION")!.getMax([])];
    expect(max[1] - min[1]).toBeCloseTo(0.1, 3);
    expect(jsonOf(plain).extensionsUsed ?? []).not.toContain("KHR_draco_mesh_compression");
  });

  it("baja calidad con menos bits ocupa menos que la alta", async () => {
    const input = await sphereGlb();
    const alta = await runClientTool("comprimir-glb", [{ name: "a.glb", bytes: input }], { metodo: "draco", calidad: "alta" }, env);
    const baja = await runClientTool("comprimir-glb", [{ name: "a.glb", bytes: input }], { metodo: "draco", calidad: "baja" }, env);
    expect(baja.outputs[0].bytes.length).toBeLessThan(alta.outputs[0].bytes.length);
    expect(DRACO_BITS.baja.quantizePosition).toBeLessThan(DRACO_BITS.alta.quantizePosition);
  });

  it("comprime con meshopt", async () => {
    const input = await sphereGlb();
    const result = await runClientTool("comprimir-glb", [{ name: "bola.glb", bytes: input }], { metodo: "meshopt", calidad: "media" }, env);
    const out = result.outputs[0];
    expect(out.bytes.length).toBeLessThan(input.length);
    expect(jsonOf(out.bytes).extensionsUsed).toContain("EXT_meshopt_compression");
    const prim = (await read(out.bytes)).getRoot().listMeshes()[0].listPrimitives()[0];
    expect(prim.getIndices()!.getCount()).toBe(120 * 120 * 6);
  });

  it("pasa las texturas a WebP y las reduce al tamaño máximo", async () => {
    const input = await sphereGlb(40, true);
    const result = await runClientTool("comprimir-glb", [{ name: "piel.glb", bytes: input }],
      { metodo: "draco", texturas: "webp", tamano_textura: 256, calidad_textura: 80 }, env);
    const out = result.outputs[0];
    const json = jsonOf(out.bytes);
    expect(json.images?.[0].mimeType).toBe("image/webp");
    expect(json.extensionsRequired).toContain("EXT_texture_webp");
    expect(out.note).toMatch(/textura/);
    const texture = (await read(await glbSinDraco({ name: "p.glb", bytes: out.bytes }, nodeWasm))).getRoot().listTextures()[0];
    expect(texture.getSize()).toEqual([256, 256]);
  });

  it("no devuelve nunca un archivo mayor que el original", async () => {
    const once = (await runClientTool("comprimir-glb", [{ name: "b.glb", bytes: await sphereGlb() }], { metodo: "draco" }, env)).outputs[0];
    const again = (await runClientTool("comprimir-glb", [{ name: "b.glb", bytes: once.bytes }], { metodo: "draco", calidad: "alta" }, env)).outputs[0];
    expect(again.bytes.length).toBeLessThanOrEqual(once.bytes.length);
  });

  it("quita la compresión para programas que no la leen", async () => {
    const draco = (await runClientTool("comprimir-glb", [{ name: "b.glb", bytes: await sphereGlb() }], { metodo: "draco" }, env)).outputs[0];
    const plain = (await runClientTool("comprimir-glb", [{ name: "b.glb", bytes: draco.bytes }], { metodo: "ninguno" }, env)).outputs[0];
    expect(jsonOf(plain.bytes).extensionsUsed ?? []).not.toContain("KHR_draco_mesh_compression");
    expect(plain.bytes.length).toBeGreaterThan(draco.bytes.length);
  });

  it("rechaza un glTF que enlaza archivos de fuera y un archivo que no es glTF", async () => {
    const gltf = new TextEncoder().encode(JSON.stringify({ asset: { version: "2.0" }, buffers: [{ uri: "modelo.bin", byteLength: 12 }] }));
    await expect(runClientTool("comprimir-glb", [{ name: "m.gltf", bytes: gltf }], {}, env)).rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
    await expect(runClientTool("comprimir-glb", [{ name: "m.glb", bytes: new Uint8Array(64) }], {}, env)).rejects.toMatchObject({ code: "CORRUPT_FILE" });
  });

  it("varios archivos salen uno a uno y en un ZIP", async () => {
    const input = await sphereGlb(30);
    const result = await runClientTool("comprimir-glb", [{ name: "a.glb", bytes: input }, { name: "b.glb", bytes: input }], {}, env);
    expect(result.outputs.map((o) => o.name)).toEqual(["a.glb", "b.glb", "modelos-glb.zip"]);
  });
});

describe("comprimir-glb: carga", () => {
  it("el índice no importa glTF Transform de forma estática (su ndarray construye funciones a partir de texto y la CSP lo prohíbe)", async () => {
    const { readFileSync } = await import("node:fs");
    const index = readFileSync(new URL("../src/index.ts", import.meta.url), "utf-8");
    expect(index).not.toMatch(/^import[^;]*from "\.\/glb"/m);
    expect(index).not.toMatch(/^export \{[^}]*\} from "\.\/glb"/m);
    expect(index).not.toMatch(/@gltf-transform/);
  });
});
