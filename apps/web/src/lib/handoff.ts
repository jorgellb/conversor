"use client";

// «Seguir con otra herramienta» (8.2): el resultado pasa a la siguiente página sin volver a subirlo ni descargarlo.
let pending: File[] = [];

export function handOff(files: File[]): void {
  pending = files;
}

export function takeHandOff(): File[] {
  const files = pending;
  pending = [];
  return files;
}
