"use client";

import { bbox, textHeight, type Obj } from "./model";

const FONT_FAMILY = { sans: "NotoSansEditor", serif: "NotoSerifEditor", mono: "NotoMonoEditor" } as const;

export function fontCss(obj: { font: "sans" | "serif" | "mono"; size: number; bold?: boolean; italic?: boolean; color: string; align?: string; lineHeight?: number }) {
  return {
    fontFamily: `${FONT_FAMILY[obj.font]}, ${obj.font === "mono" ? "monospace" : obj.font === "serif" ? "serif" : "sans-serif"}`,
    fontSize: `${obj.size}px`,
    fontWeight: obj.bold ? 700 : 400,
    fontStyle: obj.italic ? "italic" : "normal",
    color: obj.color,
    textAlign: (obj.align ?? "left") as "left" | "center" | "right",
    lineHeight: `${obj.lineHeight ?? obj.size * 1.2}px`,
    whiteSpace: "pre-wrap" as const,
    overflowWrap: "break-word" as const,
  };
}

function arrowHead(x1: number, y1: number, x2: number, y2: number, width: number): string {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = Math.max(8, width * 4);
  const a = [x2 - len * Math.cos(angle - Math.PI / 7), y2 - len * Math.sin(angle - Math.PI / 7)];
  const b = [x2 - len * Math.cos(angle + Math.PI / 7), y2 - len * Math.sin(angle + Math.PI / 7)];
  return `${x2},${y2} ${a[0]},${a[1]} ${b[0]},${b[1]}`;
}

/** Dibuja un objeto del editor en la capa SVG (mismo aspecto que tendrá en el PDF). */
export function ObjectView({ obj, editing, redaction = false }: { obj: Obj; editing: boolean; redaction?: boolean }) {
  const common = { "data-id": obj.id, style: { cursor: "move" } } as const;
  switch (obj.type) {
    case "text":
      if (editing) return null;
      return (
        <foreignObject {...common} x={obj.x} y={obj.y} width={obj.width} height={textHeight(obj)} opacity={obj.opacity ?? 1}>
          <div data-id={obj.id} style={fontCss(obj)}>{obj.text}</div>
        </foreignObject>
      );
    case "rect":
      return <rect {...common} x={obj.x} y={obj.y} width={obj.width} height={obj.height} fill={obj.fill ?? "transparent"}
        stroke={obj.stroke ?? "none"} strokeWidth={obj.strokeWidth ?? 1} opacity={obj.opacity ?? 1} />;
    case "ellipse":
      return <ellipse {...common} cx={obj.x + obj.width / 2} cy={obj.y + obj.height / 2} rx={obj.width / 2} ry={obj.height / 2}
        fill={obj.fill ?? "transparent"} stroke={obj.stroke ?? "none"} strokeWidth={obj.strokeWidth ?? 1} opacity={obj.opacity ?? 1} />;
    case "whiteout":
      // En redactar-pdf se ve semitransparente con borde rojo para revisar qué se tapa.
      return redaction
        ? <rect {...common} x={obj.x} y={obj.y} width={obj.width} height={obj.height} fill={obj.color ?? "#000000"} fillOpacity={0.55} stroke="#d00" strokeWidth={1} strokeDasharray="3 2" />
        : <rect {...common} x={obj.x} y={obj.y} width={obj.width} height={obj.height} fill={obj.color ?? "#FFFFFF"} />;
    case "line":
    case "arrow":
      return (
        <g {...common} opacity={obj.opacity ?? 1}>
          <line x1={obj.x1} y1={obj.y1} x2={obj.x2} y2={obj.y2} stroke={obj.stroke} strokeWidth={obj.strokeWidth ?? 2} strokeLinecap="round" />
          {/* zona de clic más ancha que la línea */}
          <line data-id={obj.id} x1={obj.x1} y1={obj.y1} x2={obj.x2} y2={obj.y2} stroke="transparent" strokeWidth={12} />
          {obj.type === "arrow" && <polygon points={arrowHead(obj.x1, obj.y1, obj.x2, obj.y2, obj.strokeWidth ?? 2)} fill={obj.stroke} />}
        </g>
      );
    case "polygon":
      return <polygon {...common} points={obj.points.map((p) => p.join(",")).join(" ")} fill={obj.fill ?? "transparent"}
        stroke={obj.stroke ?? "none"} strokeWidth={obj.strokeWidth ?? 1} opacity={obj.opacity ?? 1} />;
    case "ink":
      return (
        <g {...common} opacity={obj.opacity ?? 1}>
          {obj.paths.map((path, i) => (
            <polyline key={i} data-id={obj.id} points={path.map((p) => p.join(",")).join(" ")} fill="none" stroke={obj.stroke}
              strokeWidth={obj.strokeWidth ?? 2} strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </g>
      );
    case "image":
      return <image {...common} href={obj.imageUrl} x={obj.x} y={obj.y} width={obj.width} height={obj.height} preserveAspectRatio="none" opacity={obj.opacity ?? 1} />;
    case "highlight":
      return <rect {...common} x={obj.x} y={obj.y} width={obj.width} height={obj.height} fill={obj.color} opacity={obj.opacity ?? 0.4} style={{ cursor: "move", mixBlendMode: "multiply" }} />;
    case "underline":
    case "strikeout": {
      const yLine = obj.type === "underline" ? obj.y + obj.height - Math.max(1, obj.height * 0.08) : obj.y + obj.height * 0.55;
      return (
        <g {...common} opacity={obj.opacity ?? 1}>
          <rect data-id={obj.id} x={obj.x} y={obj.y} width={obj.width} height={obj.height} fill="transparent" />
          <line data-id={obj.id} x1={obj.x} y1={yLine} x2={obj.x + obj.width} y2={yLine} stroke={obj.color} strokeWidth={Math.max(1, obj.height * 0.07)} />
        </g>
      );
    }
    case "note":
      return (
        <g {...common}>
          <rect data-id={obj.id} x={obj.x} y={obj.y} width={20} height={20} rx={2} fill={obj.color ?? "#FFD54F"} stroke="#8a6d00" />
          <path data-id={obj.id} d={`M ${obj.x + 4} ${obj.y + 7} h 12 M ${obj.x + 4} ${obj.y + 11} h 12 M ${obj.x + 4} ${obj.y + 15} h 8`} stroke="#5a4500" strokeWidth={1.2} />
        </g>
      );
    case "check":
    case "cross": {
      const s = obj.size;
      const d = obj.type === "check"
        ? `M ${obj.x + 0.1 * s} ${obj.y + 0.55 * s} L ${obj.x + 0.4 * s} ${obj.y + 0.85 * s} L ${obj.x + 0.9 * s} ${obj.y + 0.15 * s}`
        : `M ${obj.x + 0.15 * s} ${obj.y + 0.15 * s} L ${obj.x + 0.85 * s} ${obj.y + 0.85 * s} M ${obj.x + 0.85 * s} ${obj.y + 0.15 * s} L ${obj.x + 0.15 * s} ${obj.y + 0.85 * s}`;
      return (
        <g {...common}>
          <rect data-id={obj.id} x={obj.x} y={obj.y} width={s} height={s} fill="transparent" />
          <path data-id={obj.id} d={d} fill="none" stroke={obj.color ?? "#000000"} strokeWidth={Math.max(1, s * 0.12)} strokeLinecap="round" />
        </g>
      );
    }
  }
}

/** Marco de selección con asas para mover el tamaño o los extremos de una línea. */
export function SelectionView({ obj }: { obj: Obj }) {
  if (obj.type === "line" || obj.type === "arrow") {
    return (
      <g>
        <circle data-handle="p1" cx={obj.x1} cy={obj.y1} r={5} fill="#fff" stroke="#c9620a" strokeWidth={1.5} style={{ cursor: "crosshair" }} />
        <circle data-handle="p2" cx={obj.x2} cy={obj.y2} r={5} fill="#fff" stroke="#c9620a" strokeWidth={1.5} style={{ cursor: "crosshair" }} />
      </g>
    );
  }
  const box = bbox(obj);
  const resizable = ["text", "rect", "ellipse", "whiteout", "image", "check", "cross", "highlight", "underline", "strikeout"].includes(obj.type);
  return (
    <g pointerEvents="none">
      <rect x={box.x - 3} y={box.y - 3} width={box.width + 6} height={box.height + 6} fill="none" stroke="#c9620a" strokeWidth={1} strokeDasharray="4 3" />
      {resizable && (
        <rect data-handle="resize" x={box.x + box.width - 1} y={box.y + box.height - 1} width={9} height={9} fill="#c9620a" pointerEvents="all"
          style={{ cursor: "nwse-resize" }} />
      )}
    </g>
  );
}
