// visor-gcode (D-257): lectura propia de G-code y bgcode por capas.
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { FEATURES, crc32, heatshrinkDecode, meatpackDecode, parseDuration, parseGcode, readBgcode } from "../src/gcode3d";

const fixture = (name: string) => new Uint8Array(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)));
const enc = (s: string) => new TextEncoder().encode(s);

describe("visor-gcode: G-code", () => {
  it("separa las capas por las marcas del laminador, con tipos, tiempo y filamento", () => {
    const model = parseGcode(fixture("pieza.gcode"));
    expect(model.layers).toHaveLength(10);
    expect(model.layers.map((l) => l.z)).toEqual([0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.6, 1.8, 2].map((z) => expect.closeTo(z, 5)));
    expect(model.stats.timeSeconds).toBe(192);
    expect(model.stats.slicer).toMatch(/^PrusaSlicer 2\.8\.1/);
    expect(model.stats.featuresUsed).toEqual(["perimetro_exterior", "perimetro_interior", "relleno", "relleno_solido"]);
    // 4 lados + 1 diagonal por capa y un círculo de 72 tramos (5° por tramo) en la capa 6.
    expect(model.layers[0].end - model.layers[0].start).toBe(5);
    expect(model.layers[5].end - model.layers[5].start).toBe(5 + 72);
    expect(model.stats.segments).toBe(10 * 5 + 72);
    expect(model.min.map((v) => Math.round(v))).toEqual([100, 100, 0]);
    expect(model.max.map((v) => Math.round(v))).toEqual([130, 120, 2]); // el círculo tiene el centro en X125
    // Relativo (M83): las retracciones y su recuperación se compensan; la extrusión es la suma de los tramos.
    expect(model.stats.filamentMm).toBeCloseTo(10 * (4 * 0.665 + 0.75) + 1.0 + 10 * 0.8, 3);
    // Los desplazamientos con salto en Z no abren capas.
    expect(model.stats.travels).toBeGreaterThan(0);
    const kinds = new Set(Array.from(model.kinds.subarray(model.layers[5].start, model.layers[5].end)).map((k) => FEATURES[k]));
    expect(kinds).toEqual(new Set(["perimetro_exterior", "relleno", "perimetro_interior"]));
  });

  it("lee el bgcode de Prusa con el mismo resultado y el tiempo de sus metadatos", () => {
    const text = parseGcode(fixture("pieza.gcode"));
    const binary = parseGcode(fixture("pieza.bgcode"));
    expect(binary.layers).toEqual(text.layers);
    expect(Array.from(binary.segments)).toEqual(Array.from(text.segments));
    expect(binary.stats.timeSeconds).toBe(192);
    const doc = readBgcode(fixture("pieza.bgcode"));
    expect(new TextDecoder().decode(doc.gcode)).toContain("G2 X130 Y110 I-5 J0 E1.0 F1200");
  });

  it("rechaza un bgcode con un bloque dañado", () => {
    const bad = fixture("pieza.bgcode");
    bad[bad.length - 10] ^= 0xff;
    expect(() => parseGcode(bad)).toThrowError(/bgcode_crc/);
  });

  it("sin marcas, las capas salen de la altura de la extrusión; absoluto, G92, pulgadas y arcos con R", () => {
    const g = ["G90", "M82", "G92 E0", "G1 Z0.3 F600", "G1 X10 Y0 E1", "G1 X10 Y10 E2", "G1 Z0.6", "G1 X0 Y10 E3",
      "G92 E0", "G1 X0 Y0 E1 ; comentario al final", "G0 Z5", "G20", "G1 X1 Y1 Z0.0354 E1.1", "G21",
      "G92 E0", "G3 X35.4 Y25.4 R10 E0.5"].join("\n");
    const model = parseGcode(enc(g));
    expect(model.layers.map((l) => Number(l.z.toFixed(2)))).toEqual([0.3, 0.6, 0.9]);
    // En pulgadas, E1.1 son 27,94 mm (desde E1): 3 + 1 + 26,94 + 0,5 del arco.
    expect(model.stats.filamentMm).toBeCloseTo(3 + 1 + (1.1 * 25.4 - 1) + 0.5, 3);
    const lastLayer = model.layers[2];
    expect(lastLayer.end - lastLayer.start).toBeGreaterThan(2); // el arco en varios tramos
    const segs = model.segments;
    const n = model.stats.segments;
    expect(segs[(n - 1) * 6 + 3]).toBeCloseTo(35.4, 4);
    expect(segs[(n - 1) * 6 + 4]).toBeCloseTo(25.4, 4);
  });

  it("Cura y Orca: tipos y tiempo", () => {
    const cura = parseGcode(enc(";FLAVOR:Marlin\n;TIME:3600\n;LAYER:0\n;TYPE:WALL-OUTER\nG1 X1 Y0 Z0.2 E1\n;TYPE:SKIN\nG1 X2 Y0 E2\n;TYPE:SUPPORT\nG1 X3 E3\n"));
    expect(cura.stats.timeSeconds).toBe(3600);
    expect(cura.stats.slicer).toBe("Cura");
    expect(cura.stats.featuresUsed).toEqual(["perimetro_exterior", "relleno_solido", "soporte"]);
    const orca = parseGcode(enc("; CHANGE_LAYER\n; FEATURE: Outer wall\nG1 X1 Y0 Z0.2 E1\n; FEATURE: Sparse infill\nG1 X2 E2\n; total estimated time: 1h 2m 3s\n"));
    expect(orca.stats.featuresUsed).toEqual(["perimetro_exterior", "relleno"]);
    expect(orca.stats.timeSeconds).toBe(3723);
  });

  it("un archivo sin extrusión no es un G-code imprimible", () => {
    expect(() => parseGcode(enc("G28\nG1 X10 Y10\n"))).toThrowError(/gcode_empty/);
  });

  it("varias herramientas y velocidad por tramo", () => {
    const model = parseGcode(enc("M83\nT0\nG1 X10 Y0 Z0.2 E1 F600\nT1\nG1 X10 Y10 E1 F1200\n"));
    expect(Array.from(model.tools)).toEqual([0, 1]);
    expect(Array.from(model.speeds)).toEqual([10, 20]);
    expect(model.stats.toolCount).toBe(2);
  });
});

describe("visor-gcode: piezas del bgcode", () => {
  it("CRC32 estándar", () => {
    expect(crc32(enc("123456789"))).toBe(0xcbf43926);
  });

  it("Heatshrink: literales y referencias, con la ventana llena de ceros al empezar", () => {
    // 1 + «A» (0x41), 1 + «B», luego referencia distancia 2 (índice 1) y longitud 4 (cuenta 3) con ventana 8 y anticipación 4.
    const bits = "1" + "01000001" + "1" + "01000010" + "0" + "00000001" + "0011";
    const bytes = new Uint8Array(Math.ceil(bits.length / 8));
    for (let k = 0; k < bits.length; k++) if (bits[k] === "1") bytes[k >> 3] |= 0x80 >> (k & 7);
    expect(new TextDecoder().decode(heatshrinkDecode(bytes, 8, 4, 6))).toBe("ABABAB");
    expect(() => heatshrinkDecode(bytes, 8, 4, 50)).toThrowError(/heatshrink/);
  });

  it("MeatPack: empaquetado, carácter entero y modo sin espacios", () => {
    const on = [0xff, 0xff, 0xfb];
    // «G1 X10\n» empaquetado: G(0xE) 1(1) │ espacio(0xB) X(0xF→entero no: X está en la tabla, 0xF es «X»?)
    const nibbles = (a: number, b: number) => a | (b << 4);
    const packed = new Uint8Array([...on, nibbles(0xd, 1), nibbles(0xb, 0xe), nibbles(1, 0), nibbles(0xc, 0xc)]);
    expect(new TextDecoder().decode(meatpackDecode(packed))).toBe("G1 X10\n");
    const full = new Uint8Array([...on, nibbles(0xd, 1), nibbles(0xb, 0xf), 0x59, nibbles(5, 0xc)]);
    expect(new TextDecoder().decode(meatpackDecode(full))).toBe("G1 Y5\n");
    // Sin espacios: 0xB es «E» y se repone el espacio antes de una letra tras una cifra.
    const nospace = new Uint8Array([...on, 0xff, 0xff, 0xf7, nibbles(0xd, 1), nibbles(0xe, 2), nibbles(0xb, 3), nibbles(0xc, 0xc)]);
    expect(new TextDecoder().decode(meatpackDecode(nospace))).toBe("G1 X2 E3\n");
  });

  it("duraciones de los laminadores", () => {
    expect(parseDuration("1d 2h 3m 4s")).toBe(93784);
    expect(parseDuration("45s")).toBe(45);
    expect(parseDuration("1234")).toBe(1234);
    expect(parseDuration("01:02:03")).toBe(3723);
    expect(parseDuration("raro")).toBeNull();
  });
});
