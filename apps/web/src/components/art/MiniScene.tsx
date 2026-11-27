// Escenas pequeñas para las cabeceras de las páginas que no son herramientas (D-265): conversor, crear PDF, ayuda,
// textos legales y la página perdida (404). SVG propio, animado solo con CSS (las clases anim-* de globals.css); se puede
// usar en componentes de servidor y de cliente (sin estado).
import type { CSSProperties, ReactNode } from "react";

export type SceneKind = "convert" | "create" | "help" | "legal" | "lost";

const d = (s: number): CSSProperties => ({ animationDelay: `${s}s` });

function Sheet({ x, y, r = 0, label, color, children }: { x: number; y: number; r?: number; label?: string; color?: string; children?: ReactNode }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${r} 26 32)`}>
      <path d="M8 0h28l16 16v42a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V6a6 6 0 0 1 6-6Z" className="s-paper" strokeWidth="1.3" />
      <path d="M36 0v10a6 6 0 0 0 6 6h10" className="s-fold" strokeWidth="1.3" />
      {label && (
        <>
          <rect x="8" y="10" width={label.length * 6 + 10} height="12" rx="6" fill={color} />
          <text x="13" y="19" fontSize="8" fontWeight="800" className="s-label" style={{ fontFamily: "var(--font-display)" }}>{label}</text>
        </>
      )}
      {children ?? (
        <g className="s-bar">
          <rect x="9" y="30" width="32" height="3.5" rx="1.75" />
          <rect x="9" y="38" width="26" height="3.5" rx="1.75" />
          <rect x="9" y="46" width="30" height="3.5" rx="1.75" />
        </g>
      )}
    </g>
  );
}

const SCENES: Record<SceneKind, ReactNode> = {
  convert: (
    <>
      <circle cx="120" cy="80" r="62" fill="none" className="s-ring anim-girar" strokeWidth="1.2" strokeDasharray="2 7" />
      <g className="anim-flotar"><Sheet x={22} y={46} r={-6} label="DOC" color="var(--c-office)" /></g>
      {[
        ["M80 78 C 110 60, 130 50, 160 34", "var(--c-pdf)"],
        ["M80 82 C 112 82, 132 82, 168 82", "var(--c-image)"],
        ["M80 86 C 110 104, 130 114, 160 128", "var(--c-data)"],
      ].map(([path, color], i) => (
        <g key={path}>
          <path d={path} fill="none" className="s-guide" strokeWidth="1.3" strokeDasharray="3 5" />
          <circle r="3.5" fill={color} className="anim-viajar" style={{ offsetPath: `path('${path}')`, ...d(i * 0.6) }} />
        </g>
      ))}
      <g className="anim-flotar" style={d(0.4)}><g transform="scale(.72)"><Sheet x={228} y={8} r={6} label="PDF" color="var(--c-pdf)" /></g></g>
      <g className="anim-flotar" style={d(1)}><g transform="scale(.72)"><Sheet x={238} y={78} r={-3} label="JPG" color="var(--c-image)" /></g></g>
      <g className="anim-flotar" style={d(1.6)}><g transform="scale(.72)"><Sheet x={228} y={150} r={5} label="XLS" color="var(--c-data)" /></g></g>
    </>
  ),
  create: (
    <>
      <circle cx="120" cy="82" r="58" fill="url(#mini-glow)" />
      <g className="anim-flotar" style={d(0.8)}><Sheet x={58} y={36} r={-14} /></g>
      <g className="anim-flotar" style={d(0.4)}><Sheet x={126} y={34} r={12} /></g>
      <g className="anim-flotar"><Sheet x={92} y={52} label="PDF" color="var(--c-pdf)" /></g>
      {[[52, 30], [196, 46], [176, 132], [46, 120]].map(([x, y], i) => (
        <path key={i} d={`M${x} ${y - 6}c.8 3.6 2.2 5 6 6-3.8 1-5.2 2.4-6 6-.8-3.6-2.2-5-6-6 3.8-1 5.2-2.4 6-6Z`} fill="var(--color-brand-500)"
          className="anim-parpadeo" style={d(i * 0.45)} />
      ))}
    </>
  ),
  help: (
    <>
      <g className="anim-girar" style={{ animationDuration: "14s" }}>
        <circle cx="120" cy="80" r="48" fill="none" stroke="var(--color-brand-500)" strokeWidth="18" />
        <circle cx="120" cy="80" r="48" fill="none" stroke="#fffaf3" strokeWidth="18" strokeDasharray="18.85 18.85" />
      </g>
      <circle cx="120" cy="80" r="39" fill="none" className="s-ring" strokeWidth="1.2" />
      <circle cx="120" cy="80" r="57" fill="none" className="s-ring" strokeWidth="1.2" />
      <text x="120" y="92" textAnchor="middle" fontSize="34" fontWeight="800" style={{ fontFamily: "var(--font-display)", fill: "var(--fg)" }}>?</text>
    </>
  ),
  legal: (
    <>
      <circle cx="120" cy="80" r="62" fill="url(#mini-glow)" />
      <path d="M120 26 82 40v34c0 25 16 44 38 52 22-8 38-27 38-52V40Z" className="s-paper anim-flotar" strokeWidth="1.6" />
      <path d="M102 80l13 13 25-27" fill="none" stroke="var(--c-ai)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"
        className="anim-dibujar" style={{ ["--len" as string]: 70, animationDelay: "0.3s" }} />
      <circle cx="120" cy="80" r="70" fill="none" className="s-ring anim-girar-rev" strokeWidth="1.2" strokeDasharray="14 8 3 8" />
    </>
  ),
  lost: (
    <>
      <path d="M16 140 C 50 120, 60 150, 96 128 S 150 96, 176 106" fill="none" className="s-guide" strokeWidth="1.5" strokeDasharray="2 7" />
      {[[30, 132], [66, 134], [104, 120]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="2.4" className="s-bar anim-parpadeo" style={d(i * 0.4)} />
      ))}
      <g className="anim-flotar">
        <Sheet x={150} y={30} r={14} label="404" color="var(--color-brand-600)">
          <text x="26" y="52" textAnchor="middle" fontSize="22" fontWeight="800" style={{ fontFamily: "var(--font-display)", fill: "var(--muted)" }}>?</text>
        </Sheet>
      </g>
      <circle cx="68" cy="56" r="20" fill="none" className="s-ring anim-girar" strokeWidth="1.2" strokeDasharray="2 6" />
      <circle cx="68" cy="56" r="7" fill="var(--c-office)" className="anim-parpadeo" />
    </>
  ),
};

export function MiniScene({ kind, className = "" }: { kind: SceneKind; className?: string }) {
  return (
    <svg viewBox="0 0 240 160" className={className} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="mini-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#e67610" stopOpacity=".22" />
          <stop offset="1" stopColor="#e67610" stopOpacity="0" />
        </radialGradient>
      </defs>
      {SCENES[kind]}
    </svg>
  );
}

/** Cabecera de página con escena (conversores, crear PDF, ayuda y textos legales). */
export function PageHero({ kind, title, intro, eyebrow, children }: {
  kind: SceneKind; title: ReactNode; intro?: ReactNode; eyebrow?: ReactNode; children?: ReactNode;
}) {
  return (
    <header className="tool-hero relative mb-2 pb-6">
      <div className="relative">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="mt-1 text-3xl font-bold sm:text-[2.5rem]">{title}</h1>
        {intro && <p className="muted mt-2 max-w-xl text-lg">{intro}</p>}
        {children}
      </div>
    </header>
  );
}
