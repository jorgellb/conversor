"use client";

// crear-collage: lienzo del editor con Konva (MIT). Dibuja la página en mm con las mismas reglas que la exportación
// (svg.ts): encuadre de cada foto, marcos, sombras, fondo y adornos. Solo se carga en el navegador (dynamic, ssr: false).
import { CAPTION, FOOTER, HEADER, MARK, captionText, cutMarks, hasHeader, pageNumberText } from "@conversor/client-tools/collage/decor";
import { STRUCTURED, cellAt, swapCells, toLocal, type PageMeta } from "@conversor/client-tools/collage/editor";
import { coverPlacement, panBy, type Cell, type CellShape, type CollageDoc, type CollagePage, type Item, type PhotoFilter, type QrItem, type TextItem } from "@conversor/client-tools/collage/model";
import { qrModules } from "@conversor/client-tools/collage/qr";
import { applyFilter, maskPath, patternLayers } from "@conversor/client-tools/collage/shapes";
import { STICKER_BY_ID } from "@conversor/client-tools/collage/stickers";
import { curvedGlyphs } from "@conversor/client-tools/collage/textcurve";
import { cellRadius, photoRect } from "@conversor/client-tools/collage/svg";
import Konva from "konva";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Ellipse, Group, Image as KImage, Layer, Line, Path, Rect, Shape, Stage, Transformer } from "react-konva";

Konva.dragDistance = 4;

export type Selection = { kind: "cell"; index: number } | { kind: "item"; id: string } | null;

export interface StagePhoto {
  bitmap: ImageBitmap | HTMLCanvasElement;
  width: number;
  height: number;
}

export interface CollageStageProps {
  doc: CollageDoc;
  pageIndex: number;
  page: CollagePage;
  /** Rótulo de las celdas vacías (ID-1: «Anverso» y «Reverso»). */
  cellLabels?: string[];
  meta: PageMeta;
  photos: Map<string, StagePhoto>;
  selection: Selection;
  /** En las plantillas libres, arrastrar dentro de la celda seleccionada encuadra la foto en lugar de moverla. */
  panMode: boolean;
  fontsVersion: number;
  label: string;
  onSelect: (selection: Selection) => void;
  /** `key` agrupa en el historial los cambios seguidos del mismo gesto. */
  onChange: (page: CollagePage, key?: string) => void;
  onDropPhoto: (id: string, cellIndex: number) => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
}

const FAMILY = { sans: "NotoSansEditor", serif: "NotoSerifEditor", mono: "NotoMonoEditor" } as const;
const SELECT = "#2563EB";
export const PHOTO_MIME = "application/x-collage-photo";

const hex = (c: string | null | undefined, fallback: string) => (c && /^#[0-9a-f]{6}$/i.test(c) ? c : fallback);

type Box = { x: number; y: number; w: number; h: number };

/** Rectángulo (con esquinas), elipse o máscara (corazón, estrella, arco) en coordenadas locales, como `shapeTag` de svg.ts. */
function Outline({ box, ellipse, radius, ...rest }: { box: Box; ellipse: boolean | CellShape; radius: number } & Konva.ShapeConfig) {
  if (typeof ellipse === "string") {
    const d = maskPath(ellipse, box);
    if (d) return <Path data={d} {...(rest as Konva.PathConfig)} />;
    ellipse = ellipse === "ellipse";
  }
  if (ellipse) return <Ellipse x={box.x + box.w / 2} y={box.y + box.h / 2} radiusX={box.w / 2} radiusY={box.h / 2} {...rest} />;
  const r = Math.max(0, Math.min(radius, box.w / 2, box.h / 2));
  return <Rect x={box.x} y={box.y} width={box.w} height={box.h} cornerRadius={r} {...rest} />;
}

function clipTo(box: Box, ellipse: boolean | CellShape, radius: number) {
  const d = typeof ellipse === "string" ? maskPath(ellipse, box) : null;
  if (typeof ellipse === "string") ellipse = ellipse === "ellipse";
  return (ctx: Konva.Context) => {
    if (d) {
      // Las máscaras (corazón, estrella, arco) las recorta PhotoShape con un Path2D; aquí basta su caja.
      ctx.beginPath();
      ctx.rect(box.x, box.y, box.w, box.h);
      ctx.closePath();
      return;
    }
    ctx.beginPath();
    if (ellipse) ctx.ellipse(box.x + box.w / 2, box.y + box.h / 2, box.w / 2, box.h / 2, 0, 0, Math.PI * 2);
    else ctx.roundRect(box.x, box.y, box.w, box.h, Math.max(0, Math.min(radius, box.w / 2, box.h / 2)));
    ctx.closePath();
  };
}

/**
 * Foto recortada a su hueco en una sola forma: la caja de la celda (para el transformador) es el hueco, no la foto
 * entera, que se sale por los lados al cubrirlo.
 */
function PhotoShape({ bitmap, area, ellipse, radius, place }: {
  bitmap: ImageBitmap | HTMLCanvasElement; area: Box; ellipse: boolean | CellShape; radius: number; place: { x: number; y: number; w: number; h: number };
}) {
  const local = { x: 0, y: 0, w: area.w, h: area.h };
  const outline = clipTo(local, ellipse, radius);
  const mask = typeof ellipse === "string" ? maskPath(ellipse, local) : null;
  return (
    <Shape x={area.x} y={area.y} width={area.w} height={area.h} perfectDrawEnabled={false}
      sceneFunc={(ctx) => {
        ctx.save();
        if (mask) {
          (ctx as unknown as { _context: CanvasRenderingContext2D })._context.clip(new Path2D(mask));
        } else {
          outline(ctx);
          ctx.clip();
        }
        ctx.drawImage(bitmap, place.x, place.y, place.w, place.h);
        ctx.restore();
      }}
      hitFunc={(ctx, shape) => {
        if (mask) {
          ctx.beginPath();
          ctx.rect(0, 0, area.w, area.h);
          ctx.closePath();
        } else {
          outline(ctx);
        }
        ctx.fillStrokeShape(shape);
      }}
    />
  );
}

/** Foto con su filtro de color (crear-tarjeta), reducida a 1600 px para que el editor vaya fluido; se guarda por foto y filtro. */
const filteredCache = new WeakMap<object, Map<string, HTMLCanvasElement>>();
export function filteredBitmap(bitmap: ImageBitmap | HTMLCanvasElement, filter: PhotoFilter | undefined): ImageBitmap | HTMLCanvasElement {
  if (!filter || filter === "ninguno" || typeof document === "undefined") return bitmap;
  let byFilter = filteredCache.get(bitmap);
  if (!byFilter) {
    byFilter = new Map();
    filteredCache.set(bitmap, byFilter);
  }
  const hit = byFilter.get(filter);
  if (hit) return hit;
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return bitmap;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
  applyFilter(data.data, filter);
  ctx.putImageData(data, 0, 0);
  byFilter.set(filter, canvas);
  return canvas;
}

/** Una línea de texto Noto Sans con su línea base en (x, y), recortada a `clip` si se da (pies de foto). */
function TextLine({ text, x, y, size, bold = false, center = false, color, clip, fontsVersion }: {
  text: string; x: number; y: number; size: number; bold?: boolean; center?: boolean; color: string; clip?: Box; fontsVersion: number;
}) {
  return (
    <Shape listening={false} fontsVersion={fontsVersion}
      sceneFunc={(ctx) => {
        ctx.save();
        if (clip) {
          ctx.beginPath();
          ctx.rect(clip.x, clip.y, clip.w, clip.h);
          ctx.closePath();
          ctx.clip();
        }
        ctx.setAttr("font", `${bold ? "bold " : ""}${size}px ${FAMILY.sans}`);
        ctx.setAttr("textAlign", center ? "center" : "left");
        ctx.setAttr("textBaseline", "alphabetic");
        ctx.setAttr("fillStyle", color);
        ctx.fillText(text.replace(/\s+/g, " "), x, y);
        ctx.restore();
      }}
    />
  );
}

function textLines(item: TextItem): string[] {
  return item.text.split(/\r?\n/).slice(0, 50).map((t) => t.replace(/\s+/g, " ").trim());
}

/** Texto con la misma línea base que la exportación: y + 0,8·tamaño y 1,25 de interlineado. */
function TextShape({ item, fontsVersion }: { item: TextItem; fontsVersion: number }) {
  return (
    <Shape
      fontsVersion={fontsVersion}
      width={item.w}
      height={item.h}
      shadowEnabled={item.shadow}
      shadowColor="#000000"
      shadowBlur={1.2}
      shadowOpacity={0.7}
      sceneFunc={(ctx) => {
        const x = item.align === "middle" ? item.w / 2 : item.align === "end" ? item.w : 0;
        ctx.setAttr("font", `${item.italic ? "italic " : ""}${item.bold ? "bold " : ""}${item.size}px ${FAMILY[item.font] ?? FAMILY.sans}`);
        ctx.setAttr("textAlign", item.align === "middle" ? "center" : item.align === "end" ? "right" : "left");
        ctx.setAttr("textBaseline", "alphabetic");
        ctx.setAttr("fillStyle", hex(item.color, "#000000"));
        const outline = item.outline && (item.outlineWidth ?? 0) > 0;
        if (outline) {
          ctx.setAttr("strokeStyle", hex(item.outline, "#FFFFFF"));
          ctx.setAttr("lineWidth", Math.min(5, item.outlineWidth!) * 2);
          ctx.setAttr("lineJoin", "round");
        }
        const curve = Math.max(-1, Math.min(1, item.curve ?? 0));
        if (curve !== 0) {
          // Como en la exportación: cada letra en su sitio del arco y con su giro.
          ctx.setAttr("textAlign", "center");
          const glyphs = curvedGlyphs(textLines(item).join(" "), { x: 0, y: 0, w: item.w, size: item.size, curve }, (ch) => ctx.measureText(ch).width);
          for (const g of glyphs) {
            if (!g.ch.trim()) continue;
            ctx.save();
            ctx.translate(g.x, g.y);
            ctx.rotate((g.angle * Math.PI) / 180);
            if (outline) ctx.strokeText(g.ch, 0, 0);
            ctx.fillText(g.ch, 0, 0);
            ctx.restore();
          }
          return;
        }
        textLines(item).forEach((line, i) => {
          if (!line) return;
          if (outline) ctx.strokeText(line, x, item.size * 0.8 + i * item.size * 1.25);
          ctx.fillText(line, x, item.size * 0.8 + i * item.size * 1.25);
        });
      }}
      hitFunc={(ctx, shape) => {
        ctx.beginPath();
        ctx.rect(0, 0, item.w, item.h);
        ctx.closePath();
        ctx.fillStrokeShape(shape);
      }}
    />
  );
}

function QrShape({ item }: { item: QrItem }) {
  const qr = qrModules(item.data);
  const side = Math.min(item.w, item.h);
  const ox = (item.w - side) / 2;
  const oy = (item.h - side) / 2;
  return (
    <>
      <Rect width={item.w} height={item.h} fill={item.background ? hex(item.background, "#FFFFFF") : "transparent"} />
      <Path data={qr.d} x={ox} y={oy} scaleX={side / qr.size} scaleY={side / qr.size} fill={hex(item.color, "#000000")} listening={false} />
    </>
  );
}

function ItemBody({ item, fontsVersion }: { item: Item; fontsVersion: number }) {
  if (item.kind === "text") return <TextShape item={item} fontsVersion={fontsVersion} />;
  if (item.kind === "qr") return <QrShape item={item} />;
  if (item.kind === "sticker") {
    const sticker = STICKER_BY_ID.get(item.sticker);
    if (!sticker) return <Rect width={item.w} height={item.h} stroke="#9CA3AF" strokeWidth={0.5} dash={[2, 2]} />;
    const sx = item.w / 100;
    const sy = item.h / 100;
    return (
      <Path data={sticker.path} scaleX={sx} scaleY={sy} fill={hex(item.color, sticker.color)} fillRule={sticker.evenodd ? "evenodd" : "nonzero"}
        stroke="rgba(0,0,0,0.15)" strokeWidth={0.6} shadowEnabled={item.shadow} shadowColor="#000000" shadowOpacity={0.35}
        shadowBlur={3 / Math.min(sx, sy)} shadowOffsetX={1.5 / sx} shadowOffsetY={2 / sy} />
    );
  }
  const stroke = hex(item.stroke, "#000000");
  const strokeWidth = Math.max(0, item.strokeWidth);
  if (item.shape === "line") {
    return (
      <>
        <Rect width={item.w} height={item.h} fill="transparent" />
        <Line points={[0, item.h / 2, item.w, item.h / 2]} stroke={stroke} strokeWidth={strokeWidth} hitStrokeWidth={Math.max(strokeWidth, 4)} />
      </>
    );
  }
  return (
    <Outline box={{ x: 0, y: 0, w: item.w, h: item.h }} ellipse={item.shape === "ellipse"} radius={0}
      fill={item.fill ? hex(item.fill, "#FFFFFF") : "transparent"} stroke={stroke} strokeWidth={strokeWidth} />
  );
}

export function CollageStage({ doc, pageIndex, page, cellLabels, meta, photos, selection, panMode, fontsVersion, label, onSelect, onChange, onDropPhoto, onKeyDown }: CollageStageProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const stage = useRef<Konva.Stage>(null);
  const transformer = useRef<Konva.Transformer>(null);
  const [available, setAvailable] = useState({ width: 600, height: 800 });
  const pan = useRef<{ index: number; start: { x: number; y: number }; cell: Cell } | null>(null);
  const structured = STRUCTURED.includes(meta.template);
  const W = doc.paper.width;
  const H = doc.paper.height;

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => setAvailable({ width: Math.max(200, (el.clientWidth || 600) - 24), height: Math.max(320, window.innerHeight * 0.78) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  // Escala px/mm: la página entera cabe en el ancho disponible y en la altura de la ventana.
  const k = Math.max(0.5, Math.min(available.width / W, available.height / H));
  const px = 1 / k;

  const selectedCell = selection?.kind === "cell" ? selection.index : -1;
  const selectedItem = selection?.kind === "item" ? selection.id : null;
  const canPan = (index: number) => index === selectedCell && Boolean(page.cells[index]?.photo) && (structured || panMode);

  // El transformador va con el adorno seleccionado o con la celda en las plantillas libres.
  useEffect(() => {
    const tr = transformer.current;
    const st = stage.current;
    if (!tr || !st) return;
    let node: Konva.Node | undefined;
    if (selectedItem) node = st.findOne(`#item-${selectedItem}`);
    else if (selectedCell >= 0 && !structured && !panMode && page.cells[selectedCell]) node = st.findOne(`#cell-${page.cells[selectedCell].id}`);
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedItem, selectedCell, structured, panMode, page]);

  useEffect(() => {
    const stop = () => {
      pan.current = null;
    };
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, []);

  const pointer = () => {
    const p = stage.current?.getPointerPosition();
    return p ? { x: p.x / k, y: p.y / k } : null;
  };

  const setCell = (index: number, patch: Partial<Cell>, key?: string) => {
    onChange({ ...page, cells: page.cells.map((c, i) => (i === index ? { ...c, ...patch } : c)) }, key);
  };

  const setItem = (id: string, patch: Partial<Item>, key?: string) => {
    onChange({ ...page, items: page.items.map((it) => (it.id === id ? ({ ...it, ...patch } as Item) : it)) }, key);
  };

  /** Lee del nodo transformado el nuevo tamaño, posición y giro (el nodo está centrado con offset). */
  const fromNode = (node: Konva.Node, box: Box) => {
    const w = Math.max(2, box.w * node.scaleX());
    const h = Math.max(2, box.h * node.scaleY());
    const sy = node.scaleY();
    node.scale({ x: 1, y: 1 });
    return { patch: { x: node.x() - w / 2, y: node.y() - h / 2, w, h, rotation: Math.round(node.rotation() * 10) / 10 }, sy };
  };

  const bg = page.background ?? doc.background;
  const angle = ((bg.angle || 0) * Math.PI) / 180;
  const half = (Math.abs(Math.cos(angle)) * W + Math.abs(Math.sin(angle)) * H) / 2;
  const bgPhoto = bg.kind === "imagen" && bg.image ? photos.get(bg.image) : undefined;
  const bgPlace = bgPhoto ? coverPlacement({ x: 0, y: 0, w: W, h: H, zoom: 1, panX: 0, panY: 0 }, bgPhoto) : null;

  const frameColor = hex(doc.frameColor, "#FFFFFF");
  const cells = useMemo(() => page.cells.map((cell, index) => ({ cell, index })), [page.cells]);
  // Tamaño real: sin sombras ni marcos (la foto mide lo que dice), con marcas de corte si se piden.
  const plain = Boolean(page.realSize);
  const frame = plain ? "ninguno" : doc.frame;
  const marks = useMemo(() => cutMarks(page), [page]);
  const margin = Math.max(0, Math.min(doc.margin, Math.min(W, H) / 3));
  const pageNumber = pageNumberText(doc, pageIndex);

  return (
    <div
      ref={wrap}
      tabIndex={0}
      role="group"
      aria-label={label}
      data-collage-stage
      className="w-full overflow-hidden rounded bg-gray-200 p-3 outline-none focus-visible:ring-2 focus-visible:ring-blue-600 dark:bg-gray-800"
      onKeyDown={onKeyDown}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(PHOTO_MIME)) e.preventDefault();
      }}
      onDrop={(e) => {
        const id = e.dataTransfer.getData(PHOTO_MIME);
        if (!id || !stage.current) return;
        e.preventDefault();
        stage.current.setPointersPositions(e.nativeEvent);
        const p = pointer();
        onDropPhoto(id, p ? cellAt(page, p.x, p.y) : -1);
      }}
    >
      <Stage
        ref={stage}
        width={Math.round(W * k)}
        height={Math.round(H * k)}
        className="mx-auto w-fit shadow-md"
        onPointerDown={(e) => {
          if (e.target === e.target.getStage() || e.target.name() === "fondo") onSelect(null);
        }}
        onPointerMove={() => {
          const state = pan.current;
          const p = pointer();
          if (!state || !p || !state.cell.photo) return;
          const photo = photos.get(state.cell.photo);
          if (!photo) return;
          const [dx, dy] = toLocal(p.x - state.start.x, p.y - state.start.y, state.cell.rotation);
          setCell(state.index, panBy({ ...state.cell, ...photoRect(state.cell) }, photo, dx, dy), "pan");
        }}
        onPointerUp={() => {
          pan.current = null;
        }}
        onWheel={(e) => {
          if (selectedCell < 0) return;
          const cell = page.cells[selectedCell];
          const p = pointer();
          if (!cell?.photo || !p || cellAt(page, p.x, p.y) !== selectedCell) return;
          e.evt.preventDefault();
          const zoom = Math.max(1, Math.min(5, cell.zoom * Math.exp(-e.evt.deltaY * 0.0015)));
          setCell(selectedCell, { zoom: Math.round(zoom * 100) / 100 }, "zoom");
        }}
      >
        <Layer scaleX={k} scaleY={k}>
          {bg.kind === "degradado" ? (
            <Rect name="fondo" width={W} height={H} preventDefault={false}
              fillLinearGradientStartPoint={{ x: W / 2 - Math.cos(angle) * half, y: H / 2 - Math.sin(angle) * half }}
              fillLinearGradientEndPoint={{ x: W / 2 + Math.cos(angle) * half, y: H / 2 + Math.sin(angle) * half }}
              fillLinearGradientColorStops={[0, hex(bg.color, "#FFFFFF"), 1, hex(bg.color2, "#E5E7EB")]} />
          ) : (
            // En el móvil, deslizar sobre el fondo desplaza la página (sobre las fotos, encuadra o intercambia).
            <Rect name="fondo" width={W} height={H} fill={hex(bg.color, "#FFFFFF")} preventDefault={false} />
          )}
          {bg.kind === "patron" && (
            <Group name="fondo" clipX={0} clipY={0} clipWidth={W} clipHeight={H} listening={false}>
              {patternLayers(bg, { x: 0, y: 0, w: W, h: H }).map((l, i) => <Path key={i} data={l.d} fill={l.fill} opacity={l.opacity} />)}
            </Group>
          )}
          {bgPhoto && bgPlace && (
            <Group name="fondo" clipX={0} clipY={0} clipWidth={W} clipHeight={H} listening={false}>
              <KImage image={bgPhoto.bitmap} x={bgPlace.x} y={bgPlace.y} width={bgPlace.w} height={bgPlace.h} />
            </Group>
          )}
          <Group>
            {cells.map(({ cell, index }) => {
              const photo = cell.photo ? photos.get(cell.photo) : undefined;
              const ellipse: CellShape = cell.shape ?? "rect";
              const radius = cellRadius(doc, cell);
              const full = { x: 0, y: 0, w: cell.w, h: cell.h };
              const caption = captionText(doc, pageIndex, index);
              const strip = cell.captionHeight ? { x: 0, y: cell.h - cell.captionHeight, w: cell.w, h: cell.captionHeight } : null;
              const r = photoRect(cell);
              const area = { x: r.x - cell.x, y: r.y - cell.y, w: r.w, h: r.h };
              const place = photo ? coverPlacement({ ...r, zoom: cell.zoom, panX: cell.panX, panY: cell.panY, fit: cell.fit }, photo) : null;
              const selected = index === selectedCell;
              const draggable = structured ? !selected : !(selected && panMode);
              const center = { x: cell.x + cell.w / 2, y: cell.y + cell.h / 2 };
              return (
                <Group key={cell.id} id={`cell-${cell.id}`} x={center.x} y={center.y} offsetX={cell.w / 2} offsetY={cell.h / 2} rotation={cell.rotation}
                  draggable={draggable}
                  onPointerDown={(e) => {
                    e.cancelBubble = true;
                    const p = pointer();
                    if (canPan(index) && p) pan.current = { index, start: p, cell };
                  }}
                  // Se selecciona al soltar sin arrastrar: si no, la celda dejaría de poder arrastrarse para intercambiarla.
                  onClick={() => {
                    if (!selected) onSelect({ kind: "cell", index });
                  }}
                  onTap={() => {
                    if (!selected) onSelect({ kind: "cell", index });
                  }}
                  onDragStart={(e) => {
                    pan.current = null;
                    if (structured) {
                      e.target.moveToTop();
                      e.target.opacity(0.75);
                    }
                  }}
                  onDragEnd={(e) => {
                    const node = e.target;
                    if (!structured) {
                      setCell(index, { x: node.x() - cell.w / 2, y: node.y() - cell.h / 2 });
                      return;
                    }
                    const p = pointer();
                    node.position(center);
                    node.opacity(1);
                    node.zIndex(index);
                    const target = p ? cellAt(page, p.x, p.y, index) : -1;
                    if (target >= 0) {
                      onChange(swapCells(page, index, target), "swap");
                      onSelect({ kind: "cell", index: target });
                    }
                  }}
                  onTransformEnd={(e) => setCell(index, fromNode(e.target, cell).patch)}
                >
                  {photo && !plain && (doc.shadow || cell.polaroid) && (
                    <Outline box={full} ellipse={ellipse} radius={radius} fill="#000000" shadowColor="#000000" shadowBlur={2.4}
                      shadowOffsetX={0.8} shadowOffsetY={1.2} shadowOpacity={0.45} />
                  )}
                  {cell.polaroid && <Outline box={full} ellipse={false} radius={radius} fill="#FFFFFF" />}
                  {photo && place ? (
                    <PhotoShape bitmap={filteredBitmap(photo.bitmap, cell.filter)} area={area} ellipse={ellipse} radius={cell.polaroid ? 0 : radius}
                      place={{ x: place.x - r.x, y: place.y - r.y, w: place.w, h: place.h }} />
                  ) : (
                    <>
                      <Outline box={area} ellipse={ellipse} radius={cell.polaroid ? 0 : radius} fill="#E5E7EB" opacity={0.85} />
                      <Line points={[area.x + area.w / 2 - 4, area.y + area.h / 2, area.x + area.w / 2 + 4, area.y + area.h / 2]} stroke="#9CA3AF" strokeWidth={1} listening={false} />
                      <Line points={[area.x + area.w / 2, area.y + area.h / 2 - 4, area.x + area.w / 2, area.y + area.h / 2 + 4]} stroke="#9CA3AF" strokeWidth={1} listening={false} />
                      {cellLabels?.[index] && (
                        <TextLine text={cellLabels[index]} x={area.x + area.w / 2} y={area.y + area.h / 2 + 10} size={Math.min(5, area.h / 6)} center
                          color="#6B7280" fontsVersion={fontsVersion} />
                      )}
                    </>
                  )}
                  {photo && (frame === "fino" || frame === "doble") && (
                    <Outline box={area} ellipse={ellipse} radius={radius} stroke={frameColor} strokeWidth={0.6} listening={false} />
                  )}
                  {photo && frame === "grueso" && <Outline box={area} ellipse={ellipse} radius={radius} stroke={frameColor} strokeWidth={2.5} listening={false} />}
                  {photo && frame === "doble" && (
                    <Outline box={{ x: area.x + 1.4, y: area.y + 1.4, w: Math.max(1, area.w - 2.8), h: Math.max(1, area.h - 2.8) }} ellipse={ellipse}
                      radius={Math.max(0, radius - 1.4)} stroke={frameColor} strokeWidth={0.6} listening={false} />
                  )}
                  {caption && strip && (
                    <TextLine text={caption} x={0.5} y={strip.y + strip.h / 2 + Math.min(CAPTION.size, strip.h * 0.6) * 0.35}
                      size={Math.min(CAPTION.size, strip.h * 0.6)} color="#111827" clip={strip} fontsVersion={fontsVersion} />
                  )}
                  {selected && <Rect width={cell.w} height={cell.h} stroke={SELECT} strokeWidth={2 * px} dash={[6 * px, 4 * px]} listening={false} />}
                </Group>
              );
            })}
          </Group>
          {page.items.map((item) => (
            <Group key={item.id} id={`item-${item.id}`} x={item.x + item.w / 2} y={item.y + item.h / 2} offsetX={item.w / 2} offsetY={item.h / 2}
              rotation={item.rotation} draggable
              onPointerDown={(e) => {
                e.cancelBubble = true;
                if (selectedItem !== item.id) onSelect({ kind: "item", id: item.id });
              }}
              onDragEnd={(e) => setItem(item.id, { x: e.target.x() - item.w / 2, y: e.target.y() - item.h / 2 })}
              onTransformEnd={(e) => {
                const { patch, sy } = fromNode(e.target, item);
                setItem(item.id, item.kind === "text" ? { ...patch, size: Math.max(1, Math.round(item.size * sy * 10) / 10) } : patch);
              }}
            >
              <ItemBody item={item} fontsVersion={fontsVersion} />
            </Group>
          ))}
          {page.documentation && hasHeader(doc) && (
            <>
              <TextLine text={doc.header!.trim()} x={W / 2} y={margin + HEADER.size * 0.8 + 1} size={HEADER.size} bold center color="#111827" fontsVersion={fontsVersion} />
              <Line points={[margin, margin + HEADER.height - 3, W - margin, margin + HEADER.height - 3]} stroke="#9CA3AF" strokeWidth={0.3} listening={false} />
            </>
          )}
          {pageNumber && (
            <TextLine text={pageNumber} x={W / 2} y={H - margin - FOOTER.height / 2 + FOOTER.size * 0.35} size={FOOTER.size} center color="#4B5563"
              fontsVersion={fontsVersion} />
          )}
          {marks.map(([x1, y1, x2, y2], i) => (
            <Line key={`m${i}`} points={[x1, y1, x2, y2]} stroke="#000000" strokeWidth={MARK.width} listening={false} />
          ))}
          <Transformer ref={transformer} rotationSnaps={[0, 90, 180, 270]} flipEnabled={false} ignoreStroke borderStroke={SELECT} anchorStroke={SELECT}
            anchorSize={10} keepRatio={selectedItem !== null && page.items.find((it) => it.id === selectedItem)?.kind !== "shape"}
            boundBoxFunc={(old, next) => (Math.abs(next.width) < 8 || Math.abs(next.height) < 8 ? old : next)} />
        </Layer>
      </Stage>
    </div>
  );
}
