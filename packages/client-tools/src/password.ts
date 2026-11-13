// generar-contrasena (A.6): crypto.getRandomValues con muestreo por rechazo, sin sesgo de módulo.
import { ToolError, type ToolResult } from "./common";

export interface ContrasenaOptions {
  longitud: number;
  mayusculas: boolean;
  minusculas: boolean;
  numeros: boolean;
  simbolos: boolean;
  excluir_ambiguos: boolean;
  cantidad: number;
}

export type RandomFill = (buffer: Uint32Array<ArrayBuffer>) => Uint32Array<ArrayBuffer>;

const SETS = {
  mayusculas: "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  minusculas: "abcdefghijklmnopqrstuvwxyz",
  numeros: "0123456789",
  simbolos: "!#$%&()*+,-./:;<=>?@[]^_{|}~",
} as const;

const AMBIGUOUS = new Set(["0", "O", "o", "1", "l", "I", "|"]);

const defaultFill: RandomFill = (buffer) => globalThis.crypto.getRandomValues(buffer);

/** Entero uniforme en [0, n): descarta los valores de la cola que causarían sesgo. */
export function randomInt(n: number, fill: RandomFill = defaultFill): number {
  if (!Number.isInteger(n) || n <= 0 || n > 2 ** 32) throw new RangeError("n fuera de rango");
  const limit = Math.floor(2 ** 32 / n) * n;
  const buf = new Uint32Array(new ArrayBuffer(4));
  for (;;) {
    fill(buf);
    if (buf[0] < limit) return buf[0] % n;
  }
}

function shuffle<T>(items: T[], fill: RandomFill): T[] {
  for (let i = items.length - 1; i > 0; i -= 1) {
    const j = randomInt(i + 1, fill);
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}

export function generarUna(o: ContrasenaOptions, fill: RandomFill = defaultFill): string {
  const pools = (Object.keys(SETS) as (keyof typeof SETS)[])
    .filter((k) => o[k])
    .map((k) => Array.from(SETS[k]).filter((c) => !o.excluir_ambiguos || !AMBIGUOUS.has(c)));
  if (!pools.length) throw new ToolError("INVALID_OPTIONS", "Elige al menos un tipo de carácter");
  const length = Math.min(64, Math.max(8, Math.floor(o.longitud)));
  if (length < pools.length) throw new ToolError("INVALID_OPTIONS", "Longitud demasiado corta");
  const all = pools.flat();
  // Un carácter de cada grupo elegido y el resto del conjunto completo; después se baraja.
  const chars = pools.map((pool) => pool[randomInt(pool.length, fill)]);
  while (chars.length < length) chars.push(all[randomInt(all.length, fill)]);
  return shuffle(chars, fill).join("");
}

/** Bits de entropía aproximados (se muestran junto a la contraseña). */
export function entropyBits(o: ContrasenaOptions): number {
  const size = (Object.keys(SETS) as (keyof typeof SETS)[])
    .filter((k) => o[k])
    .reduce((n, k) => n + Array.from(SETS[k]).filter((c) => !o.excluir_ambiguos || !AMBIGUOUS.has(c)).length, 0);
  return size ? Math.floor(o.longitud * Math.log2(size)) : 0;
}

export function generarContrasena(o: ContrasenaOptions, fill: RandomFill = defaultFill): ToolResult {
  const count = Math.min(20, Math.max(1, Math.floor(o.cantidad || 1)));
  const passwords = Array.from({ length: count }, () => generarUna(o, fill));
  return { outputs: [], notes: [`≈ ${entropyBits(o)} bits`], display: passwords };
}
