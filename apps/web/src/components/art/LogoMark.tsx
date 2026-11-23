import { useId } from "react";

// Marca del sitio (D-265): una hoja con la esquina doblada y una flecha que da la vuelta (convertir), dibujada a trazos.
export function LogoMark({ size = 34, animated = true }: { size?: number; animated?: boolean }) {
  const draw = animated ? "anim-dibujar" : "";
  const gradient = `logo-${useId().replace(/:/g, "")}`; // la marca sale en la cabecera y en el pie: ids distintos
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false" className="shrink-0">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f08a2b" />
          <stop offset="1" stopColor="#b35609" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="36" height="36" rx="11" fill={`url(#${gradient})`} />
      <path d="M13 9.5h9.5l5.5 5.5v15.5a1.5 1.5 0 0 1-1.5 1.5h-13.5a1.5 1.5 0 0 1-1.5-1.5v-19.5a1.5 1.5 0 0 1 1.5-1.5Z"
        fill="#fffaf3" />
      <path d="M22.5 9.5v4.5a1 1 0 0 0 1 1h4.5" fill="#f6d2ad" />
      <path className={draw} style={{ ["--len" as string]: 40 }} d="M15.5 23.5a5 5 0 0 1 8.7-3.4" fill="none" stroke="#b35609"
        strokeWidth="2.2" strokeLinecap="round" />
      <path className={draw} style={{ ["--len" as string]: 40, animationDelay: "0.25s" }} d="M24.5 22.5a5 5 0 0 1-8.7 3.4" fill="none"
        stroke="#1a1c22" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M24.8 17.6l-0.4 2.7-2.7-0.5" fill="none" stroke="#b35609" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15.2 28.4l0.4-2.7 2.7 0.5" fill="none" stroke="#1a1c22" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
