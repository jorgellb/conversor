// Iconos de categoría (D-265): trazos propios de 24 px en `currentColor`; al pasar por su tarjeta, cada uno se mueve a
// su manera (las clases ico-* de globals.css, solo sin «reducir movimiento»).
import type { CSSProperties, ReactNode } from "react";

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function delay(s: number): CSSProperties {
  return { animationDelay: `${s}s` };
}

const ICONS: Record<string, ReactNode> = {
  pdf: (
    <>
      <path {...stroke} d="M7 3.5h7l4 4v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1Z" />
      <path {...stroke} d="M14 3.5v4h4" />
      <path {...stroke} className="ico-draw" d="M9 12h6M9 15h6M9 18h3.5" />
    </>
  ),
  office: (
    <>
      <rect {...stroke} x="4" y="4" width="16" height="16" rx="2" />
      <path {...stroke} d="M4 9h16M9.5 9v11" />
      <path {...stroke} className="ico-draw" d="M12 12.5h5M12 15.5h5M12 18h3" />
    </>
  ),
  image: (
    <>
      <rect {...stroke} x="3.5" y="5" width="17" height="14" rx="2" />
      <circle {...stroke} className="ico-hover" cx="9" cy="10" r="1.8" />
      <path {...stroke} d="m4 17.5 5-5 3.5 3.5 2.5-2.5 5 4.5" />
    </>
  ),
  audio: (
    <>
      {[5, 8.5, 12, 15.5, 19].map((x, i) => (
        <path key={x} {...stroke} className="ico-beat" style={delay(i * 0.12)} d={`M${x} ${[14, 9, 5, 8, 13][i]}v${[4, 10, 14, 10, 5][i]}`} />
      ))}
    </>
  ),
  video: (
    <>
      <rect {...stroke} x="3" y="5.5" width="18" height="13" rx="2.5" />
      <path {...stroke} d="M3 9h18M3 15h18" opacity=".45" />
      <path className="ico-hover" d="M10.5 9.8v4.4a.5.5 0 0 0 .76.43l3.6-2.2a.5.5 0 0 0 0-.86l-3.6-2.2a.5.5 0 0 0-.76.43Z" fill="currentColor" />
    </>
  ),
  ai: (
    <>
      <path {...stroke} className="ico-hover" d="M11 3.5c.6 3.6 2.3 5.3 5.9 5.9-3.6.6-5.3 2.3-5.9 5.9-.6-3.6-2.3-5.3-5.9-5.9 3.6-.6 5.3-2.3 5.9-5.9Z" />
      <path {...stroke} className="ico-spin" d="M17.5 14.5c.3 1.6 1 2.3 2.6 2.6-1.6.3-2.3 1-2.6 2.6-.3-1.6-1-2.3-2.6-2.6 1.6-.3 2.3-1 2.6-2.6Z" />
      <circle cx="6" cy="18" r="1.2" fill="currentColor" />
    </>
  ),
  data: (
    <>
      <path {...stroke} d="M4 20h16" />
      {[6.5, 10.5, 14.5, 18.5].map((x, i) => (
        <path key={x} {...stroke} strokeWidth={2.4} className="ico-beat" style={delay(i * 0.15)} d={`M${x} 19v-${[6, 11, 8, 13][i]}`} />
      ))}
    </>
  ),
  "3d": (
    <g className="ico-hover">
      <path {...stroke} d="m12 3.5 7.5 4.2v8.6L12 20.5l-7.5-4.2V7.7Z" />
      <path {...stroke} d="m4.5 7.7 7.5 4.2 7.5-4.2M12 11.9v8.6" />
    </g>
  ),
  sign: (
    <>
      <path {...stroke} d="m14.5 4.5 5 5-9 9H5.5v-5Z" />
      <path {...stroke} d="m12.5 6.5 5 5" />
      <path {...stroke} className="ico-draw" d="M4 21c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3-1.5 6 0" />
    </>
  ),
  invoice: (
    <>
      <path {...stroke} d="M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3Z" />
      <path {...stroke} className="ico-draw" d="M9 8h6M9 11h6" />
      <path {...stroke} d="M14.5 14.6a2.4 2.4 0 1 0 0 2.8M9.5 15.5h4" />
    </>
  ),
  convert: (
    <g className="ico-spin">
      <path {...stroke} d="M5 12a7 7 0 0 1 12-4.9M19 12a7 7 0 0 1-12 4.9" />
      <path {...stroke} d="M17.4 3.8 17 7.2l-3.3-.5M6.6 20.2l.4-3.4 3.3.5" />
    </g>
  ),
};

export function CategoryIcon({ id, size = 24, className = "" }: { id: string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={className}>
      {ICONS[id] ?? ICONS.convert}
    </svg>
  );
}

/** El color de la categoría para la tarjeta o el icono (variables --c-* de globals.css). */
export function categoryColor(id: string): CSSProperties {
  return { ["--c" as string]: `var(--c-${ICONS[id] ? id : "convert"})` };
}
