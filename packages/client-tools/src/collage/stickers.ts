// Stickers propios de crear-collage (A.1): trazados sencillos dibujados para este proyecto, en una caja de 100 × 100.
// Sin recursos de terceros.

function star(points: number, outer: number, inner: number, cx = 50, cy = 52): string {
  const parts: string[] = [];
  for (let i = 0; i < points * 2; i += 1) {
    const r = i % 2 === 0 ? outer : inner;
    const a = -Math.PI / 2 + (i * Math.PI) / points;
    parts.push(`${i === 0 ? "M" : "L"}${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return `${parts.join(" ")} Z`;
}

const circle = (cx: number, cy: number, r: number) => `M${cx + r} ${cy} A${r} ${r} 0 1 0 ${cx - r} ${cy} A${r} ${r} 0 1 0 ${cx + r} ${cy} Z`;

function sun(): string {
  const rays: string[] = [];
  for (let i = 0; i < 12; i += 1) {
    const a = (i * Math.PI) / 6;
    const p = (r: number, da: number) => `${(50 + r * Math.cos(a + da)).toFixed(2)} ${(50 + r * Math.sin(a + da)).toFixed(2)}`;
    rays.push(`M${p(30, -0.12)} L${p(47, 0)} L${p(30, 0.12)} Z`);
  }
  return `${circle(50, 50, 24)} ${rays.join(" ")}`;
}

function flower(): string {
  const petals: string[] = [];
  for (let i = 0; i < 6; i += 1) {
    const a = (i * Math.PI) / 3;
    petals.push(circle(+(50 + 26 * Math.cos(a)).toFixed(2), +(50 + 26 * Math.sin(a)).toFixed(2), 19));
  }
  return petals.join(" ");
}

export interface Sticker {
  id: string;
  es: string;
  en: string;
  path: string;
  /** Regla de relleno (los que tienen agujeros usan evenodd). */
  evenodd?: boolean;
  /** Color por defecto. */
  color: string;
}

export const STICKERS: Sticker[] = [
  { id: "corazon", es: "Corazón", en: "Heart", color: "#E11D48",
    path: "M50 89 C22 68 5 51 5 31 C5 16 16 6 29 6 C39 6 46 12 50 20 C54 12 61 6 71 6 C84 6 95 16 95 31 C95 51 78 68 50 89 Z" },
  { id: "estrella", es: "Estrella", en: "Star", color: "#F59E0B", path: star(5, 48, 20) },
  { id: "destello", es: "Destello", en: "Sparkle", color: "#FBBF24",
    path: "M50 4 C54 34 66 46 96 50 C66 54 54 66 50 96 C46 66 34 54 4 50 C34 46 46 34 50 4 Z" },
  { id: "sol", es: "Sol", en: "Sun", color: "#F97316", path: sun() },
  { id: "flor", es: "Flor", en: "Flower", color: "#EC4899", path: `${flower()} ${circle(50, 50, 14)}` },
  { id: "bocadillo", es: "Bocadillo", en: "Speech bubble", color: "#FFFFFF",
    path: "M14 10 H86 Q94 10 94 18 V62 Q94 70 86 70 H44 L26 90 L30 70 H14 Q6 70 6 62 V18 Q6 10 14 10 Z" },
  { id: "flecha", es: "Flecha", en: "Arrow", color: "#2563EB", path: "M6 40 H60 V20 L94 50 L60 80 V60 H6 Z" },
  { id: "corona", es: "Corona", en: "Crown", color: "#EAB308", path: "M8 76 L14 28 L34 50 L50 14 L66 50 L86 28 L92 76 Z M8 82 H92 V92 H8 Z" },
  { id: "globo", es: "Globo", en: "Balloon", color: "#8B5CF6",
    path: "M50 6 C72 6 86 24 86 44 C86 64 68 78 50 80 C32 78 14 64 14 44 C14 24 28 6 50 6 Z M45 80 L55 80 L50 87 Z" },
  { id: "cinta", es: "Cinta", en: "Ribbon", color: "#DC2626", path: "M2 34 H20 V74 H2 L10 54 Z M98 34 H80 V74 H98 L90 54 Z M14 26 H86 V66 H14 Z" },
  { id: "visto", es: "Visto", en: "Tick", color: "#16A34A", evenodd: true,
    path: `${circle(50, 50, 46)} M26 52 L42 68 L76 34 L69 27 L42 54 L33 45 Z` },
  { id: "nota", es: "Nota musical", en: "Music note", color: "#111827",
    path: "M60 8 L88 4 V18 L66 22 V70 C66 82 54 90 43 88 C32 86 28 78 32 70 C36 62 48 59 58 64 V8 Z" },
];

export const STICKER_BY_ID = new Map(STICKERS.map((s) => [s.id, s]));
