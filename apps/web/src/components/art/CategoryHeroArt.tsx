import type { CSSProperties } from "react";

import { CategoryIcon } from "./CategoryIcon";

// Ilustración del apartado de cada categoría (D-272): la marca de la categoría en el centro, dos anillos que giran
// despacio y los formatos que más usa flotando alrededor. Solo transform y opacity, en pausa hasta hidratar y quieta con
// «reducir movimiento» (clases anim-* de globals.css).
const SPOTS = [
  [70, 62, -6], [292, 52, 5], [318, 168, -4], [250, 232, 6], [52, 196, 4], [168, 22, -3],
] as const;

export function CategoryHeroArt({ id, formats }: { id: string; formats: string[] }) {
  return (
    <svg viewBox="0 0 360 260" className="h-auto w-full" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={`cat-halo-${id}`} cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="var(--c)" stopOpacity=".28" />
          <stop offset="1" stopColor="var(--c)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`cat-tile-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--c)" stopOpacity=".95" />
          <stop offset="1" stopColor="var(--c)" stopOpacity=".72" />
        </linearGradient>
      </defs>
      <circle cx="180" cy="130" r="130" fill={`url(#cat-halo-${id})`} />
      <circle className="anim-girar" cx="180" cy="130" r="92" fill="none" stroke="var(--c)" strokeOpacity=".35" strokeWidth="1.5" strokeDasharray="2 9" strokeLinecap="round" />
      <circle className="anim-girar-rev" cx="180" cy="130" r="118" fill="none" stroke="var(--c)" strokeOpacity=".2" strokeWidth="1.5" strokeDasharray="36 12 4 12" />
      <g className="anim-flotar" style={{ ["--r" as string]: "0deg" } as CSSProperties}>
        <rect x="132" y="82" width="96" height="96" rx="28" fill="var(--c)" opacity=".18" transform="translate(6 10)" />
        <rect x="132" y="82" width="96" height="96" rx="28" fill={`url(#cat-tile-${id})`} />
        <rect x="132.5" y="82.5" width="95" height="95" rx="27.5" fill="none" stroke="#fff" strokeOpacity=".35" />
        <g transform="translate(152 102)" className="cat-art-ico">
          <CategoryIcon id={id} size={56} />
        </g>
      </g>
      {formats.slice(0, SPOTS.length).map((f, i) => {
        const [x, y, r] = SPOTS[i];
        const w = 34 + f.length * 9.6;
        return (
          <g key={f} className="anim-flotar" style={{ ["--r" as string]: `${r}deg`, animationDelay: `${-i * 1.1}s`, transformOrigin: `${x}px ${y}px` } as CSSProperties}>
            <rect x={x - w / 2} y={y - 14} width={w} height="28" rx="14" className="s-paper" strokeWidth="1" />
            <circle cx={x - w / 2 + 13} cy={y} r="3.5" fill="var(--c)" />
            <text x={x - w / 2 + 23} y={y + 4.5} fontSize="12.5" fontWeight="800" letterSpacing=".04em" fill="currentColor"
              style={{ fontFamily: "var(--font-display)" }}>{f}</text>
          </g>
        );
      })}
      {[[110, 120], [262, 104], [214, 214]].map(([x, y], i) => (
        <path key={i} className="anim-parpadeo" style={{ animationDelay: `${i * 0.7}s` }} fill="var(--c)"
          d={`M${x} ${y - 7}c.6 4 2.3 5.6 6 6.2-3.7.6-5.4 2.2-6 6.2-.6-4-2.3-5.6-6-6.2 3.7-.6 5.4-2.2 6-6.2Z`} />
      ))}
    </svg>
  );
}
