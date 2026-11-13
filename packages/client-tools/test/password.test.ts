import { describe, expect, it } from "vitest";

import { entropyBits, generarUna, randomInt } from "../src/password";
import { runClientTool } from "../src/index";

const BASE = { longitud: 16, mayusculas: true, minusculas: true, numeros: true, simbolos: false, excluir_ambiguos: false, cantidad: 1 };

describe("generar-contrasena", () => {
  it("respeta la longitud e incluye todos los tipos elegidos", () => {
    for (let i = 0; i < 200; i += 1) {
      const p = generarUna({ ...BASE, simbolos: true });
      expect(p).toHaveLength(16);
      expect(p).toMatch(/[A-Z]/);
      expect(p).toMatch(/[a-z]/);
      expect(p).toMatch(/[0-9]/);
      expect(p).toMatch(/[^A-Za-z0-9]/);
    }
  });

  it("excluye los caracteres ambiguos", () => {
    const all = Array.from({ length: 300 }, () => generarUna({ ...BASE, excluir_ambiguos: true, longitud: 64 })).join("");
    expect(all).not.toMatch(/[0O1lI|o]/);
  });

  it("muestreo por rechazo: descarta la cola sesgada", () => {
    // Para n = 3, el límite es 4294967295 - (2^32 mod 3) = 4294967295 - 1; el valor máximo se descarta.
    const values = [0xffffffff, 7];
    const fill = (buf: Uint32Array<ArrayBuffer>) => {
      buf[0] = values.shift()!;
      return buf;
    };
    expect(randomInt(3, fill)).toBe(7 % 3);
  });

  it("distribución uniforme aproximada (chi cuadrado)", () => {
    const counts = new Array(10).fill(0);
    const n = 50000;
    for (let i = 0; i < n; i += 1) counts[randomInt(10)] += 1;
    const expected = n / 10;
    const chi = counts.reduce((s, c) => s + (c - expected) ** 2 / expected, 0);
    // 9 grados de libertad: 27,88 es el percentil 99,9.
    expect(chi).toBeLessThan(27.88);
  });

  it("varias contraseñas y entropía", async () => {
    const res = await runClientTool("generar-contrasena", [], { ...BASE, cantidad: 5 });
    expect(res.display).toHaveLength(5);
    expect(new Set(res.display ?? []).size).toBe(5);
    expect(entropyBits(BASE)).toBe(Math.floor(16 * Math.log2(62)));
    await expect(runClientTool("generar-contrasena", [], { ...BASE, mayusculas: false, minusculas: false, numeros: false })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });
});
