// Tipos mínimos de gifenc 1.0.3 (el paquete no los publica).
declare module "gifenc" {
  export type GifFormat = "rgb565" | "rgb444" | "rgba4444";
  export type Palette = number[][];
  export function quantize(rgba: Uint8Array | Uint8ClampedArray, maxColors: number, opts?: {
    format?: GifFormat; oneBitAlpha?: boolean | number; clearAlpha?: boolean; clearAlphaThreshold?: number; clearAlphaColor?: number;
  }): Palette;
  export function applyPalette(rgba: Uint8Array | Uint8ClampedArray, palette: Palette, format?: GifFormat): Uint8Array;
  export interface GifEncoderStream {
    writeFrame(index: Uint8Array, width: number, height: number, opts?: {
      palette?: Palette; transparent?: boolean; transparentIndex?: number; delay?: number; repeat?: number; dispose?: number; first?: boolean;
    }): void;
    finish(): void;
    bytes(): Uint8Array;
    bytesView(): Uint8Array;
    reset(): void;
  }
  export function GIFEncoder(opts?: { auto?: boolean; initialCapacity?: number }): GifEncoderStream;
}
