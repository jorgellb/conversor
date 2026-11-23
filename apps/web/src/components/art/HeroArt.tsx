// Ilustración de la portada (D-265): el «taller» donde un archivo entra y sale convertido. Seis hojas de formatos distintos
// flotan alrededor de un anillo que gira; por las guías viajan puntos de un formato a otro. Solo SVG y CSS (transform,
// opacity y offset-path), sin JavaScript; con «reducir movimiento» se queda quieta.
import type { CSSProperties, ReactNode } from "react";

type Sheet = { x: number; y: number; r: number; color: string; label: string; delay: number; body: ReactNode };

const SHEETS: Sheet[] = [
  { x: 40, y: 54, r: -7, color: "var(--c-pdf)", label: "PDF", delay: 0, body: <Lines /> },
  { x: 372, y: 34, r: 6, color: "var(--c-office)", label: "DOCX", delay: 1.2, body: <Lines short /> },
  { x: 404, y: 236, r: -4, color: "var(--c-image)", label: "JPG", delay: 2.1, body: <Picture /> },
  { x: 22, y: 262, r: 5, color: "var(--c-audio)", label: "MP3", delay: 0.6, body: <Wave /> },
  { x: 214, y: 330, r: -3, color: "var(--c-3d)", label: "STL", delay: 1.7, body: <Cube /> },
  { x: 206, y: -4, r: 3, color: "var(--c-data)", label: "XLSX", delay: 2.6, body: <Grid /> },
];

function Lines({ short = false }: { short?: boolean }) {
  return (
    <g className="s-bar">
      <rect x="14" y="44" width="56" height="5" rx="2.5" />
      <rect x="14" y="56" width={short ? 40 : 62} height="5" rx="2.5" />
      <rect x="14" y="68" width="50" height="5" rx="2.5" />
      <rect x="14" y="80" width={short ? 58 : 36} height="5" rx="2.5" />
    </g>
  );
}

function Picture() {
  return (
    <g>
      <rect x="14" y="42" width="62" height="44" rx="6" className="s-well" />
      <circle cx="34" cy="56" r="6" fill="var(--c-audio)" className="anim-parpadeo" />
      <path d="M16 84l18-18 12 12 9-9 19 15" fill="none" stroke="var(--c-image)" strokeWidth="3" strokeLinejoin="round" />
    </g>
  );
}

function Wave() {
  const bars = [16, 30, 44, 24, 38, 20, 34, 12];
  return (
    <g>
      {bars.map((h, i) => (
        <rect key={i} x={16 + i * 8} y={84 - h} width="4" height={h} rx="2" fill="var(--c-audio)" className="anim-latir"
          style={{ animationDelay: `${i * 0.12}s` }} />
      ))}
    </g>
  );
}

function Cube() {
  return (
    <g className="anim-flotar" style={{ animationDuration: "5s" }}>
      <path d="M46 40l24 13v26L46 92 22 79V53Z" fill="color-mix(in srgb, var(--c-3d) 18%, var(--paper))" stroke="var(--c-3d)" strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M22 53l24 13 24-13M46 66v26" fill="none" stroke="var(--c-3d)" strokeWidth="2.5" strokeLinejoin="round" />
    </g>
  );
}

function Grid() {
  return (
    <g fill="none" stroke="var(--c-data)" strokeWidth="2">
      <rect x="14" y="42" width="62" height="44" rx="4" />
      <path d="M14 56h62M14 70h62M35 42v44M55 42v44" />
      <rect x="36" y="57" width="18" height="12" fill="color-mix(in srgb, var(--c-data) 25%, transparent)" stroke="none" />
    </g>
  );
}

function SheetCard({ s }: { s: Sheet }) {
  // El giro de la hoja va en su grupo interior: la animación solo la sube y la baja.
  const style: CSSProperties = { animationDelay: `${s.delay}s`, transformBox: "fill-box", transformOrigin: "center" };
  return (
    <g transform={`translate(${s.x} ${s.y})`}>
      <g className="anim-flotar" style={style}>
        <g transform={`rotate(${s.r} 45 55)`}>
          <rect x="3" y="6" width="90" height="106" rx="12" className="s-shadow" />
          <path d="M12 0h52l26 26v76a10 10 0 0 1-10 10H12A10 10 0 0 1 2 102V10A10 10 0 0 1 12 0Z" className="s-paper" strokeWidth="1.5" />
          <path d="M64 0v18a8 8 0 0 0 8 8h18" className="s-fold" strokeWidth="1.5" />
          <rect x="12" y="14" width={s.label.length * 8 + 14} height="18" rx="9" fill={s.color} />
          <text x="19" y="27" fontSize="11" fontWeight="800" className="s-label" letterSpacing=".5" style={{ fontFamily: "var(--font-display)" }}>{s.label}</text>
          {s.body}
        </g>
      </g>
    </g>
  );
}

// Guías de un formato al anillo y del anillo a otro: los puntos viajan por ellas (offset-path).
const PATHS = [
  "M100 120 C 170 150, 200 190, 260 210",
  "M420 100 C 360 140, 330 170, 260 210",
  "M90 320 C 160 300, 200 260, 260 210",
  "M260 210 C 330 240, 380 270, 440 300",
  "M260 210 C 262 270, 262 320, 262 360",
  "M260 210 C 258 150, 256 110, 252 60",
];

export function HeroArt({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 520 460" className={className} role="img" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="hero-core" cx="50%" cy="45%" r="60%">
          <stop offset="0" stopColor="#ffb26b" />
          <stop offset=".55" stopColor="#e67610" />
          <stop offset="1" stopColor="#a14d07" />
        </radialGradient>
        <radialGradient id="hero-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#e67610" stopOpacity=".35" />
          <stop offset="1" stopColor="#e67610" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* Halo y anillos que giran en sentidos opuestos */}
      <circle cx="260" cy="210" r="170" fill="url(#hero-glow)" />
      <circle cx="260" cy="210" r="132" fill="none" className="s-ring anim-girar" strokeWidth="1.5" strokeDasharray="2 9" />
      <circle cx="260" cy="210" r="98" fill="none" className="s-ring anim-girar-rev" strokeWidth="1.5" strokeDasharray="22 10 4 10" />
      {/* Guías y puntos viajeros */}
      {PATHS.map((d, i) => (
        <g key={d}>
          <path d={d} fill="none" className="s-guide" strokeWidth="1.5" strokeDasharray="3 6" />
          <circle r="4" fill={["var(--c-pdf)", "var(--c-office)", "var(--c-audio)", "var(--c-image)", "var(--c-3d)", "var(--c-data)"][i]}
            className="anim-viajar" style={{ offsetPath: `path('${d}')`, animationDelay: `${i * 0.75}s` }} />
        </g>
      ))}
      {/* El núcleo: la prensa que convierte */}
      <g>
        <circle cx="260" cy="210" r="58" fill="url(#hero-core)" />
        <circle cx="260" cy="210" r="58" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
        <g className="anim-girar" style={{ animationDuration: "9s" }}>
          <path d="M236 200a26 26 0 0 1 44-12" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" />
          <path d="M284 220a26 26 0 0 1-44 12" fill="none" stroke="#1a1c22" strokeWidth="5" strokeLinecap="round" />
          <path d="M281 178l-1 11-11-2" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M239 242l1-11 11 2" fill="none" stroke="#1a1c22" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      </g>
      {SHEETS.map((s) => <SheetCard key={s.label} s={s} />)}
      {/* Destellos */}
      {[[150, 60], [470, 170], [70, 200], [330, 420], [490, 40]].map(([x, y], i) => (
        <path key={i} d={`M${x} ${y - 8}c1 5 3 7 8 8-5 1-7 3-8 8-1-5-3-7-8-8 5-1 7-3 8-8Z`} fill="var(--color-brand-500)"
          className="anim-parpadeo" style={{ animationDelay: `${i * 0.5}s` }} />
      ))}
    </svg>
  );
}
