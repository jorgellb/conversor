// Fondo de la cabecera de cada herramienta (D-265): retícula de puntos de imprenta, arcos y un halo con el color de su
// categoría (`--c`). Quieto a propósito: una máscara y una trama de este tamaño animadas se repintan en cada fotograma y
// retrasaban la hidratación de la herramienta (el primer archivo elegido se perdía).
export function ToolHeroDecor() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="xMaxYMid slice" viewBox="0 0 800 260"
      aria-hidden="true" focusable="false">
      <defs>
        <pattern id="puntos" width="18" height="18" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.1" className="s-bar" opacity=".55" />
        </pattern>
        <radialGradient id="halo" cx="85%" cy="20%" r="55%">
          <stop offset="0" stopColor="var(--c)" stopOpacity=".22" />
          <stop offset="1" stopColor="var(--c)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="desvanecer" x1="0" x2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset=".45" stopColor="#fff" stopOpacity=".9" />
        </linearGradient>
        <mask id="mascara">
          <rect width="800" height="260" fill="url(#desvanecer)" />
        </mask>
      </defs>
      <rect width="800" height="260" fill="url(#halo)" />
      <rect width="800" height="260" fill="url(#puntos)" mask="url(#mascara)" />
      <g fill="none" stroke="var(--c)" strokeOpacity=".35" strokeWidth="1.5">
        <circle cx="700" cy="70" r="90" strokeDasharray="3 10" />
        <circle cx="700" cy="70" r="140" strokeDasharray="40 14 6 14" strokeOpacity=".22" />
        <path d="M520 240c40-60 120-90 200-80" strokeDasharray="4 8" strokeOpacity=".3" />
      </g>
      <circle cx="700" cy="70" r="7" fill="var(--c)" />
    </svg>
  );
}
