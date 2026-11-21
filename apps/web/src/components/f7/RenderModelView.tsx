"use client";
// render-modelo-3d (7.20, F7-H, D-257): una imagen PNG de cada modelo con three.js en el navegador. Un único
// renderizador fuera de pantalla (con alfa para el fondo transparente) del tamaño pedido; el modelo se encuadra desde el
// ángulo elegido. WebGL en un OffscreenCanvas dentro de un worker no sirve aquí: el 3MF y el AMF necesitan DOMParser.
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { zipSync } from "three/examples/jsm/libs/fflate.module.js";

import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

import { OptionsForm, defaultsOf } from "../OptionsForm";
import { addEnvironment, addLights, canvasPng, frameCamera, isModel, loadModel, ModelError, overrideColor, placeOnFloor, type ViewAngle } from "./model3d";

type Values = Record<string, unknown>;
interface Rendered {
  name: string;
  url: string;
  bytes: Uint8Array;
}

export interface RenderOptions {
  tamano: number;
  angulo: ViewAngle;
  fondo: "transparente" | "blanco" | "color";
  color_fondo: string;
  color_modelo: "original" | "propio";
  color: string;
  eje_vertical: "auto" | "y" | "z";
}

/** Pinta un modelo ya cargado en un lienzo de `size` px y devuelve el PNG. */
export async function renderToPng(root: THREE.Object3D, o: RenderOptions): Promise<Uint8Array> {
  const size = Math.max(64, Math.min(2048, Number(o.tamano) || 1024));
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  } catch {
    throw new ModelError("NO_WEBGL");
  }
  try {
    renderer.setPixelRatio(1);
    renderer.setSize(size, size, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    if (o.fondo !== "transparente") scene.background = new THREE.Color(o.fondo === "blanco" ? "#ffffff" : o.color_fondo);
    addLights(scene);
    await addEnvironment(scene, renderer);
    scene.add(root);
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 10000);
    frameCamera(camera, new THREE.Box3().setFromObject(root, true), o.angulo, 1.05);
    renderer.setClearColor(0x000000, 0);
    renderer.render(scene, camera);
    scene.remove(root);
    return new Uint8Array(await (await canvasPng(canvas)).arrayBuffer());
  } finally {
    renderer.dispose();
    renderer.forceContextLoss();
  }
}

export function RenderModelView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("visor3d");
  const tt = useTranslations("tool");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<Values>(() => defaultsOf(properties));
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<Rendered[]>([]);
  const [zip, setZip] = useState<string | null>(null);
  const [running, setRunning] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = rememberedOptions(spec.slug);
    if (Object.keys(saved).length) setValues((v) => ({ ...v, ...saved }));
  }, [spec.slug]);

  useEffect(() => () => {
    results.forEach((r) => URL.revokeObjectURL(r.url));
    if (zip) URL.revokeObjectURL(zip);
  }, [results, zip]);

  const models = files.filter((f) => isModel(f.name));

  async function run() {
    if (!models.length) return;
    rememberOptions(spec.slug, values, spec.secretFields);
    const o = values as unknown as RenderOptions;
    setRunning(0);
    setErrors([]);
    const done: Rendered[] = [];
    const failed: string[] = [];
    for (const [i, main] of models.entries()) {
      setRunning(i / models.length);
      try {
        const loaded = await loadModel(main, files.filter((f) => f !== main), { missing: (name) => t("missing", { name }), ktx2: t("ktx2") }, o.eje_vertical);
        try {
          placeOnFloor(loaded.root);
          if (o.color_modelo === "propio") overrideColor(loaded.root, o.color);
          const bytes = await renderToPng(loaded.root, o);
          done.push({ name: `${main.name.replace(/\.[^.]+$/, "")}.png`, bytes, url: URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: "image/png" })) });
        } finally {
          loaded.dispose();
        }
      } catch (err) {
        if (err instanceof ModelError && err.code === "NO_WEBGL") {
          failed.push(t("noWebgl"));
          break;
        }
        failed.push(`${main.name}: ${err instanceof ModelError && err.code === "MISSING" ? t("error.MISSING", { names: err.message }) : t(`error.${err instanceof ModelError ? err.code : "CORRUPT_FILE"}`)}`);
      }
    }
    setResults(done);
    setErrors(failed);
    if (done.length > 1) {
      const used = new Set<string>();
      const tree: Record<string, [Uint8Array, { level: 0 }]> = {};
      for (const r of done) {
        let name = r.name;
        for (let n = 2; used.has(name); n++) name = r.name.replace(/\.png$/, `-${n}.png`);
        used.add(name);
        tree[name] = [r.bytes, { level: 0 }];
      }
      setZip(URL.createObjectURL(new Blob([new Uint8Array(zipSync(tree))], { type: "application/zip" })));
    } else setZip(null);
    setRunning(null);
    setStatus(t("rendered", { n: done.length }));
    if (done.length) recordUse(spec.slug);
  }

  const background = values.fondo === "transparente" ? "repeating-conic-gradient(#e5e7eb 0 25%, #fff 0 50%) 50% / 16px 16px"
    : values.fondo === "blanco" ? "#fff" : String(values.color_fondo);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <div className="card flex flex-col gap-3 p-4"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files).slice(0, spec.maxFiles ?? 20)); }}>
          <button type="button" className="btn" onClick={() => fileRef.current?.click()} data-render-open>{t("openModels")}</button>
          <input ref={fileRef} type="file" multiple className="sr-only" aria-label={t("openModels")} data-render-input
            accept=".stl,.obj,.mtl,.3mf,.ply,.glb,.gltf,.bin,.amf,.png,.jpg,.jpeg,.webp"
            onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, spec.maxFiles ?? 20)); e.target.value = ""; }} />
          <p className="muted text-sm">{models.length ? t("chosen", { n: models.length }) : t("formats")}</p>
        </div>
        <section aria-label={tt("options")}>
          <h2 className="mb-2 font-semibold">{tt("options")}</h2>
          <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields} moreLabel={t("moreOptions")} />
        </section>
        <button type="button" className="btn" disabled={!models.length || running !== null} onClick={() => void run()} data-render-run>
          {running !== null ? t("rendering", { pct: Math.round(running * 100) }) : t("render")}
        </button>
        <p className="muted text-xs">{t("privacy")}</p>
      </div>
      <aside className="flex flex-col gap-4" aria-label={tt("result")}>
        <div aria-live="polite" className="sr-only">{status}</div>
        {errors.map((e) => <p key={e} role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300">{e}</p>)}
        {results.length > 0 && (
          <section className="card flex flex-col gap-3 p-4">
            <h2 className="font-semibold">{tt("result")}</h2>
            {zip && <a className="btn" href={zip} download="renders.zip" data-render-zip>{t("downloadAll")}</a>}
            <ul className="grid grid-cols-2 gap-3">
              {results.map((r) => (
                <li key={r.url} className="flex flex-col gap-1">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={r.url} alt={r.name} className="aspect-square w-full rounded border object-contain" style={{ background }} data-render-image />
                  <a className="text-sm underline" href={r.url} download={r.name}>{t("download", { name: r.name })}</a>
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  );
}
