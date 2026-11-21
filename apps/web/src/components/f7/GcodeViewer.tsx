"use client";
// visor-gcode (7.20, F7-H, D-257): G-code y bgcode capa a capa con three.js. El worker lee el archivo (lector propio,
// sin código de los visores AGPL de PrusaSlicer u OrcaSlicer) y devuelve los tramos en búferes; aquí se dibujan como
// líneas y se muestra un rango de capas con `setDrawRange`, sin copiar nada. Color por tipo de extrusión, herramienta o
// velocidad; desplazamientos opcionales; reproducción de la capa de arriba con la boquilla.
import type { Feature, GcodeModel } from "@conversor/client-tools";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { askWorker, ClientToolError } from "@/lib/client-runner";
import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

import { canvasPng, frameCamera } from "./model3d";
import { useThreeView } from "./useThreeView";

const FEATURE_LIST: Feature[] = ["perimetro_exterior", "perimetro_interior", "voladizo", "relleno", "relleno_solido", "superior", "inferior",
  "puente", "hueco", "falda", "soporte", "interfaz_soporte", "torre", "planchado", "otro"];
export const FEATURE_COLORS: Record<Feature, number> = {
  perimetro_exterior: 0xf59e0b, perimetro_interior: 0xfacc15, voladizo: 0x2563eb, relleno: 0xb91c1c, relleno_solido: 0xa21caf,
  superior: 0xef4444, inferior: 0x7c3aed, puente: 0x0891b2, hueco: 0xf9fafb, falda: 0x059669, soporte: 0x16a34a,
  interfaz_soporte: 0x65a30d, torre: 0x9ca3af, planchado: 0xfb7185, otro: 0x6b7280,
};
const TOOL_COLORS = [0xf59e0b, 0x2563eb, 0x16a34a, 0xdc2626, 0x7c3aed, 0x0891b2, 0xdb2777, 0x4b5563];
type ColorMode = "tipo" | "herramienta" | "velocidad";

/** Color de los vértices en el espacio lineal: three.js los trata como lineales y los pasa a sRGB al pintar (D-260: con
 * los bytes sRGB tal cual salían más claros que la leyenda). */
function linear(color: THREE.Color): [number, number, number] {
  return [Math.round(color.r * 255), Math.round(color.g * 255), Math.round(color.b * 255)];
}

function rgb(hex: number): [number, number, number] {
  return linear(new THREE.Color(hex));
}

/** Del azul (lento) al rojo (rápido), en una tabla de 256 colores. */
const SPEED_LUT: [number, number, number][] = Array.from({ length: 256 }, (_, k) =>
  linear(new THREE.Color().setHSL((1 - k / 255) * 0.66, 0.85, 0.5, THREE.SRGBColorSpace)));

function colorsFor(model: GcodeModel, mode: ColorMode): Uint8Array {
  const n = model.stats.segments;
  const out = new Uint8Array(n * 6);
  const featureRgb = FEATURE_LIST.map((f) => rgb(FEATURE_COLORS[f]));
  const toolRgb = TOOL_COLORS.map(rgb);
  // Velocidad: del percentil 2 al 98, para que unos pocos tramos muy rápidos no lo dejen todo azul.
  let lo = 0, hi = model.stats.maxSpeed || 1;
  if (mode === "velocidad" && n) {
    const sample = Array.from({ length: Math.min(n, 20000) }, (_, k) => model.speeds[Math.floor((k * n) / Math.min(n, 20000))]).sort((a, b) => a - b);
    lo = sample[Math.floor(sample.length * 0.02)];
    hi = Math.max(lo + 1, sample[Math.floor(sample.length * 0.98)]);
  }
  const span = 255 / (hi - lo);
  for (let i = 0; i < n; i++) {
    const c = mode === "tipo" ? featureRgb[model.kinds[i]] ?? featureRgb[14]
      : mode === "herramienta" ? toolRgb[model.tools[i] % toolRgb.length]
        : SPEED_LUT[Math.max(0, Math.min(255, Math.round((model.speeds[i] - lo) * span)))];
    out[i * 6] = out[i * 6 + 3] = c[0];
    out[i * 6 + 1] = out[i * 6 + 4] = c[1];
    out[i * 6 + 2] = out[i * 6 + 5] = c[2];
  }
  return out;
}

function formatDuration(seconds: number | null, locale: string): string {
  if (seconds === null) return "—";
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = Math.round(seconds % 60);
  return h ? `${h} h ${m} min` : m ? `${m} min ${s} s` : `${s} s`.replace(".", locale === "es" ? "," : ".");
}

export function GcodeViewer({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("visor3d");
  const te = useTranslations("errors");
  const locale = useLocale();
  const { mountRef, view, failed } = useThreeView();
  const [model, setModel] = useState<GcodeModel | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [range, setRange] = useState<[number, number]>([0, 0]);
  const [onlyTop, setOnlyTop] = useState(false);
  const [travels, setTravels] = useState(false);
  const [mode, setMode] = useState<ColorMode>("tipo");
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(1);
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const modeRef = useRef(mode);
  const shownMode = useRef<{ model: GcodeModel | null; mode: ColorMode }>({ model: null, mode });
  const objects = useRef<{ root: THREE.Group; lines: THREE.LineSegments; travel: THREE.LineSegments; nozzle: THREE.Mesh } | null>(null);

  const request = useRef(0);

  async function open(file: File | undefined) {
    if (!file || !view) return;
    const mine = ++request.current; // si se abre otro mientras tanto, este resultado ya no cuenta (D-260)
    setError("");
    setPlaying(false);
    setLoading(0);
    try {
      const parsed = await askWorker<GcodeModel>("__gcode", file, {}, undefined, (f) => setLoading(f));
      if (mine !== request.current) return;
      setModel(parsed);
      setName(file.name);
      setRange([0, parsed.layers.length - 1]);
      setProgress(1);
      setStatus(t("gcodeOpened", { name: file.name, layers: parsed.layers.length }));
      recordUse(spec.slug);
    } catch (err) {
      if (mine !== request.current) return;
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      const detail = err instanceof Error ? err.message : "";
      setError(/gcode_empty/.test(detail) ? t("gcodeEmpty") : /bgcode_crc|bgcode_/.test(detail) ? t("bgcodeDamaged") : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      if (mine === request.current) setLoading(null);
    }
  }

  // Geometría: un solo búfer de tramos (y otro de desplazamientos), girado para que Z del G-code quede arriba.
  useEffect(() => {
    if (!view || !model) return;
    const root = new THREE.Group();
    root.rotation.x = -Math.PI / 2;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(model.segments, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colorsFor(model, modeRef.current), 3, true));
    shownMode.current = { model, mode: modeRef.current };
    const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true }));
    lines.frustumCulled = false;
    const tGeometry = new THREE.BufferGeometry();
    tGeometry.setAttribute("position", new THREE.BufferAttribute(model.travels, 3));
    const travel = new THREE.LineSegments(tGeometry, new THREE.LineBasicMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.45 }));
    travel.frustumCulled = false;
    const span = Math.max(model.max[0] - model.min[0], model.max[1] - model.min[1], 10);
    const nozzle = new THREE.Mesh(new THREE.ConeGeometry(span / 120, span / 40, 16), new THREE.MeshStandardMaterial({ color: 0xdc2626 }));
    nozzle.rotation.x = -Math.PI / 2; // la punta hacia abajo en el sistema del G-code (Z arriba)
    nozzle.visible = false;
    root.add(lines, travel, nozzle);
    // Cama: un plano con rejilla de 10 mm bajo la pieza.
    const bed = new THREE.GridHelper(Math.ceil((span * 1.4) / 10) * 10, Math.ceil((span * 1.4) / 10), 0x9ca3af, 0xd1d5db);
    bed.rotation.x = Math.PI / 2;
    bed.position.set((model.min[0] + model.max[0]) / 2, (model.min[1] + model.max[1]) / 2, 0);
    root.add(bed);
    view.scene.add(root);
    objects.current = { root, lines, travel, nozzle };
    root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(lines);
    frameCamera(view.camera, box, "isometrico");
    view.controls.target.copy(box.getCenter(new THREE.Vector3()));
    view.controls.update();
    view.invalidate();
    return () => {
      view.scene.remove(root);
      geometry.dispose();
      tGeometry.dispose();
      (lines.material as THREE.Material).dispose();
      (travel.material as THREE.Material).dispose();
      nozzle.geometry.dispose();
      (nozzle.material as THREE.Material).dispose();
      bed.geometry.dispose();
      objects.current = null;
    };
  }, [view, model]);

  useEffect(() => {
    modeRef.current = mode;
    const o = objects.current;
    if (!o || !model) return;
    if (shownMode.current.model === model && shownMode.current.mode === mode) return; // ya calculado al cargar
    shownMode.current = { model, mode };
    const attr = o.lines.geometry.getAttribute("color") as THREE.BufferAttribute;
    (attr.array as Uint8Array).set(colorsFor(model, mode));
    attr.needsUpdate = true;
    view?.invalidate();
  }, [mode, model, view]);

  // Rango de capas visible, desplazamientos y avance de la reproducción dentro de la capa de arriba.
  useEffect(() => {
    const o = objects.current;
    if (!o || !model) return;
    const top = model.layers[range[1]];
    const bottom = model.layers[onlyTop ? range[1] : range[0]];
    const visibleEnd = top.start + Math.round((top.end - top.start) * progress);
    o.lines.geometry.setDrawRange(bottom.start * 2, Math.max(0, visibleEnd - bottom.start) * 2);
    o.travel.visible = travels;
    o.travel.geometry.setDrawRange(bottom.travelStart * 2, Math.max(0, top.travelEnd - bottom.travelStart) * 2);
    const last = visibleEnd - 1;
    o.nozzle.visible = progress < 1 && last >= top.start;
    if (o.nozzle.visible) {
      const s = model.segments;
      o.nozzle.position.set(s[last * 6 + 3], s[last * 6 + 4], s[last * 6 + 5] + (o.nozzle.geometry as THREE.ConeGeometry).parameters.height / 2);
    }
    view?.invalidate();
  }, [model, range, onlyTop, travels, progress, view]);

  // Reproducción: recorre la capa de arriba en unos 6 s y pasa a la siguiente (con refs: sin efectos dentro de los
  // actualizadores de estado, que React puede llamar dos veces).
  const progressRef = useRef(progress);
  const rangeRef = useRef(range);
  progressRef.current = progress;
  rangeRef.current = range;
  useEffect(() => {
    if (!playing || !model) return;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const next = progressRef.current + dt / 6;
      if (next >= 1) {
        const [lo, hi] = rangeRef.current;
        if (hi + 1 >= model.layers.length) {
          setProgress(1);
          setPlaying(false);
          return;
        }
        rangeRef.current = [lo, hi + 1];
        progressRef.current = 0;
        setRange([lo, hi + 1]);
        setProgress(0);
      } else {
        progressRef.current = next;
        setProgress(next);
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, model]);

  async function capture() {
    if (!view) return;
    view.renderer.render(view.scene, view.camera);
    const blob = await canvasPng(view.renderer.domElement);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${name.replace(/\.[^.]+$/, "") || "gcode"}-${locale === "en" ? "layer" : "capa"}-${range[1] + 1}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 30_000);
  }

  const legend = useMemo(() => {
    if (!model) return [];
    if (mode === "tipo") return model.stats.featuresUsed.map((f) => ({ key: f, label: t(`feature.${f}`), color: FEATURE_COLORS[f] }));
    if (mode === "herramienta") return Array.from({ length: model.stats.toolCount }, (_, k) => ({ key: String(k), label: `T${k}`, color: TOOL_COLORS[k % TOOL_COLORS.length] }));
    return [];
  }, [model, mode, t]);

  const top = model?.layers[range[1]];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn" onClick={() => fileRef.current?.click()} data-gcode-open>{t("openGcode")}</button>
        <input ref={fileRef} type="file" className="sr-only" accept=".gcode,.gco,.g,.bgcode" aria-label={t("openGcode")} data-gcode-input
          onChange={(e) => { void open(e.target.files?.[0]); e.target.value = ""; }} />
        <p className="muted text-sm">{t("gcodeFormats")}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <div className="card relative h-[min(70vh,40rem)] min-h-80 overflow-hidden p-0"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void open(e.dataTransfer.files[0]); }}>
          <div ref={mountRef} className="h-full w-full" role="img" aria-label={model ? t("gcodeCanvas", { name, layer: range[1] + 1 }) : t("canvasEmpty")} data-gcode-canvas />
          {!model && loading === null && !failed && <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6 text-center"><p className="muted">{t("dropGcode")}</p></div>}
          {loading !== null && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/60 dark:bg-black/40">
              <p>{t("reading")}</p>
              <progress max={1} value={loading} className="w-48" aria-label={t("reading")} />
            </div>
          )}
          {failed && <p role="alert" className="absolute inset-0 flex items-center justify-center p-6 text-center">{t("noWebgl")}</p>}
        </div>
        <aside className="flex flex-col gap-4" aria-label={t("tools")}>
          {model && top && (
            <section className="card flex flex-col gap-1 p-4 text-sm" data-gcode-info>
              <h2 className="mb-1 font-semibold">{name}</h2>
              <p data-gcode-layers>{t("layerOf", { n: range[1] + 1, total: model.layers.length })} · Z {top.z.toLocaleString(locale, { maximumFractionDigits: 3 })} mm</p>
              <p>{t("printTime")}: {formatDuration(model.stats.timeSeconds, locale)}</p>
              <p>{t("filament")}: {(model.stats.filamentMm / 1000).toLocaleString(locale, { maximumFractionDigits: 2 })} m</p>
              {model.stats.slicer && <p>{t("slicer")}: {model.stats.slicer}</p>}
              <p className="muted text-xs">{t("segments", { n: model.stats.segments.toLocaleString(locale) })}</p>
              {model.stats.truncated && <p className="text-amber-700 dark:text-amber-300">{t("truncated")}</p>}
            </section>
          )}
          <section className="card flex flex-col gap-3 p-4 text-sm">
            <label className="flex flex-col gap-1">
              <span>{t("topLayer", { n: range[1] + 1 })}</span>
              <input type="range" min={0} max={Math.max(0, (model?.layers.length ?? 1) - 1)} value={range[1]} disabled={!model} data-gcode-top
                onChange={(e) => { const v = Number(e.target.value); setRange(([lo]) => [Math.min(lo, v), v]); setProgress(1); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span>{t("bottomLayer", { n: range[0] + 1 })}</span>
              <input type="range" min={0} max={Math.max(0, (model?.layers.length ?? 1) - 1)} value={range[0]} disabled={!model || onlyTop}
                onChange={(e) => { const v = Number(e.target.value); setRange(([, hi]) => [v, Math.max(hi, v)]); }} />
            </label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={onlyTop} onChange={(e) => setOnlyTop(e.target.checked)} />{t("onlyTop")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={travels} onChange={(e) => setTravels(e.target.checked)} data-gcode-travels />{t("travels")}</label>
            <label className="flex flex-col gap-1">
              <span>{t("colorBy")}</span>
              <select className="input" value={mode} onChange={(e) => setMode(e.target.value as ColorMode)} data-gcode-mode>
                <option value="tipo">{t("colorType")}</option>
                <option value="herramienta">{t("colorTool")}</option>
                <option value="velocidad">{t("colorSpeed")}</option>
              </select>
            </label>
            {legend.length > 0 && (
              <ul className="flex flex-col gap-1" aria-label={t("legend")} data-gcode-legend>
                {legend.map((l) => (
                  <li key={l.key} className="flex items-center gap-2">
                    <span aria-hidden className="inline-block h-3 w-3 rounded-sm border" style={{ background: `#${l.color.toString(16).padStart(6, "0")}` }} />{l.label}
                  </li>
                ))}
              </ul>
            )}
            {mode === "velocidad" && <p className="muted text-xs">{t("speedLegend")}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" disabled={!model} data-gcode-play
                onClick={() => { if (!playing && progress >= 1) setProgress(0); setPlaying(!playing); }}>{playing ? t("pause") : t("play")}</button>
              <button type="button" className="btn-secondary btn" disabled={!model} onClick={() => void capture()}>{t("capture")}</button>
            </div>
          </section>
          <p className="muted text-xs">{t("privacyGcode")}</p>
        </aside>
      </div>
      <div aria-live="polite" className="sr-only">{status}</div>
      {error && <p role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300" data-gcode-error>{error}</p>}
    </div>
  );
}
