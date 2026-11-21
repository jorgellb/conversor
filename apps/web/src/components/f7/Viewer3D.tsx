"use client";
// visor-3d (7.20, F7-H, D-257): STL, OBJ+MTL, 3MF, PLY, GLB/glTF y AMF con three.js, sin subir nada. Órbita, vistas,
// rejilla y medidas de la caja, alambre, sección por un plano, color, medir entre dos puntos y captura PNG.
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

import { boundsOf, canvasPng, eachMaterial, formatMm, frameCamera, isModel, loadModel, ModelError, overrideColor, placeOnFloor,
  type LoadedModel, type ViewAngle } from "./model3d";
import { useThreeView } from "./useThreeView";

type Axis = "x" | "y" | "z";
const ANGLES: ViewAngle[] = ["isometrico", "frontal", "superior", "lateral"];

export function Viewer3D({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("visor3d");
  const locale = useLocale();
  const { mountRef, view, failed } = useThreeView();
  const [files, setFiles] = useState<File[]>([]);
  const [current, setCurrent] = useState(0);
  const [model, setModel] = useState<LoadedModel | null>(null);
  const [box, setBox] = useState<THREE.Box3 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [wireframe, setWireframe] = useState(false);
  const [grid, setGrid] = useState(true);
  const [showBox, setShowBox] = useState(false);
  const [section, setSection] = useState<Axis | "">("");
  const [sectionAt, setSectionAt] = useState(50);
  const [color, setColor] = useState<string>("");
  const [up, setUp] = useState<"auto" | "y" | "z">("auto");
  const [measuring, setMeasuring] = useState(false);
  const [distance, setDistance] = useState<number | null>(null);
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const helpers = useRef<THREE.Group>(new THREE.Group());
  const measure = useRef<{ points: THREE.Vector3[]; group: THREE.Group }>({ points: [], group: new THREE.Group() });
  const plane = useRef(new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0));

  const models = files.filter((f) => isModel(f.name));

  // Abrir el modelo elegido.
  useEffect(() => {
    if (!view) return;
    const main = models[current];
    if (!main) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setDistance(null);
    // Una medida no puede unir puntos de dos modelos (D-260).
    measure.current.points = [];
    measure.current.group.clear();
    (async () => {
      try {
        const loaded = await loadModel(main, files.filter((f) => f !== main), { missing: (name) => t("missing", { name }), ktx2: t("ktx2") }, up);
        if (cancelled) {
          loaded.dispose();
          return;
        }
        const placed = placeOnFloor(loaded.root);
        setModel((old) => {
          if (old) {
            view.scene.remove(old.root);
            old.dispose();
          }
          return loaded;
        });
        view.scene.add(loaded.root);
        setBox(placed);
        frameCamera(view.camera, placed, "isometrico");
        view.controls.target.copy(placed.getCenter(new THREE.Vector3()));
        view.controls.update();
        view.invalidate();
        setStatus(t("opened", { name: main.name }));
        recordUse(spec.slug);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ModelError && err.code === "MISSING" ? t("error.MISSING", { names: err.message })
            : t(`error.${err instanceof ModelError ? err.code : "CORRUPT_FILE"}`));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, files, current, up]);

  // Rejilla, caja con medidas y marcas de medición.
  useEffect(() => {
    if (!view || !box) return;
    const group = helpers.current;
    group.remove(measure.current.group);
    group.traverse((o) => {
      const helper = o as THREE.LineSegments;
      if (helper.geometry) helper.geometry.dispose();
      const mat = helper.material as THREE.Material | THREE.Material[] | undefined;
      if (mat) (Array.isArray(mat) ? mat : [mat]).forEach((m) => m.dispose());
    });
    group.clear();
    view.scene.add(group);
    const size = box.getSize(new THREE.Vector3());
    if (grid) {
      const span = Math.max(size.x, size.z) * 1.6;
      const step = span > 1000 ? 100 : span > 200 ? 10 : span > 40 ? 5 : 1;
      const cells = Math.max(2, Math.ceil(span / step));
      const gridHelper = new THREE.GridHelper(cells * step, cells, 0x9ca3af, 0xd1d5db);
      gridHelper.position.y = box.min.y - size.y * 0.001;
      group.add(gridHelper);
    }
    if (showBox) group.add(new THREE.Box3Helper(box, 0xe67610));
    group.add(measure.current.group);
    view.invalidate();
  }, [view, box, grid, showBox]);

  useEffect(() => {
    if (!model || !view) return;
    eachMaterial(model.root, (m) => {
      (m as THREE.MeshStandardMaterial).wireframe = wireframe;
    });
    view.invalidate();
  }, [model, view, wireframe]);

  useEffect(() => {
    if (!model || !view) return;
    overrideColor(model.root, color || null);
    eachMaterial(model.root, (m) => {
      (m as THREE.MeshStandardMaterial).wireframe = wireframe;
    });
    view.invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, view, color]);

  // Sección: el plano deja ver lo que queda por debajo de la posición elegida en el eje.
  useEffect(() => {
    if (!model || !view || !box) return;
    const axis = section ? new THREE.Vector3(section === "x" ? -1 : 0, section === "y" ? -1 : 0, section === "z" ? -1 : 0) : null;
    if (axis) {
      const lo = box.min[section as Axis], hi = box.max[section as Axis];
      plane.current.normal.copy(axis);
      plane.current.constant = lo + ((hi - lo) * sectionAt) / 100;
    }
    eachMaterial(model.root, (m) => {
      const data = m.userData as { side?: THREE.Side };
      data.side ??= m.side; // se devuelve al quitar la sección
      m.clippingPlanes = axis ? [plane.current] : null;
      m.side = axis ? THREE.DoubleSide : data.side;
      m.needsUpdate = true;
    });
    view.invalidate();
  }, [model, view, box, section, sectionAt, color]);

  const setAngle = useCallback((angle: ViewAngle) => {
    if (!view || !box) return;
    const center = frameCamera(view.camera, box, angle);
    view.controls.target.copy(center);
    view.controls.update();
    view.invalidate();
  }, [view, box]);

  // Medir: dos clics sobre el modelo (sin arrastrar) dan la distancia entre los puntos.
  useEffect(() => {
    if (!view || !model || !measuring) return;
    const canvas = view.renderer.domElement;
    let downAt: [number, number] | null = null;
    const down = (e: PointerEvent) => { downAt = [e.clientX, e.clientY]; };
    const upHandler = (e: PointerEvent) => {
      if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return;
      const rect = canvas.getBoundingClientRect();
      const pointer = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      const ray = new THREE.Raycaster();
      ray.setFromCamera(pointer, view.camera);
      const hit = ray.intersectObject(model.root, true).find((h) => !section || plane.current.distanceToPoint(h.point) >= 0);
      if (!hit) return;
      const m = measure.current;
      if (m.points.length >= 2) {
        m.points = [];
        m.group.traverse((o) => {
          const obj = o as THREE.Mesh;
          obj.geometry?.dispose();
          (obj.material as THREE.Material | undefined)?.dispose?.();
        });
        m.group.clear();
      }
      m.points.push(hit.point.clone());
      const radius = Math.max(box!.getSize(new THREE.Vector3()).length() / 300, 0.05);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(radius, 12, 8), new THREE.MeshBasicMaterial({ color: 0xdc2626, depthTest: false }));
      dot.renderOrder = 10;
      dot.position.copy(hit.point);
      m.group.add(dot);
      if (m.points.length === 2) {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(m.points), new THREE.LineBasicMaterial({ color: 0xdc2626, depthTest: false }));
        line.renderOrder = 10;
        m.group.add(line);
        const d = m.points[0].distanceTo(m.points[1]);
        setDistance(d);
        setStatus(t("distance", { value: formatMm(d, locale) }));
      } else setDistance(null);
      view.invalidate();
    };
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", upHandler);
    return () => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", upHandler);
    };
  }, [view, model, measuring, box, section, locale, t]);

  useEffect(() => {
    if (measuring) return;
    measure.current.points = [];
    measure.current.group.clear();
    setDistance(null);
    view?.invalidate();
  }, [measuring, view]);

  async function capture() {
    if (!view || !model) return;
    view.renderer.render(view.scene, view.camera);
    const blob = await canvasPng(view.renderer.domElement);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${model.name.replace(/\.[^.]+$/, "")}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 30_000);
    setStatus(t("captured"));
  }

  function pick(list: FileList | null) {
    if (!list?.length) return;
    const chosen = Array.from(list).slice(0, spec.maxFiles ?? 20);
    if (!chosen.some((f) => isModel(f.name))) {
      setError(t("error.UNSUPPORTED_FORMAT"));
      return;
    }
    setFiles(chosen);
    setCurrent(0);
    setSection("");
    setMeasuring(false);
  }

  const size = box?.getSize(new THREE.Vector3());
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn" onClick={() => fileRef.current?.click()} data-visor-open>{t("open")}</button>
        <input ref={fileRef} type="file" multiple className="sr-only" aria-label={t("open")} data-visor-input
          accept=".stl,.obj,.mtl,.3mf,.ply,.glb,.gltf,.bin,.amf,.png,.jpg,.jpeg,.webp"
          onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
        {models.length > 1 && (
          <label className="flex items-center gap-2 text-sm">
            <span>{t("model")}</span>
            <select className="input w-auto" value={current} onChange={(e) => setCurrent(Number(e.target.value))}>
              {models.map((f, i) => <option key={f.name + i} value={i}>{f.name}</option>)}
            </select>
          </label>
        )}
        <p className="muted text-sm">{t("formats")}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <div className="card relative h-[min(70vh,40rem)] min-h-80 overflow-hidden p-0"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files); }}>
          <div ref={mountRef} className="h-full w-full" role="img" aria-label={model ? t("canvasModel", { name: model.name }) : t("canvasEmpty")} data-visor-canvas />
          {!model && !loading && !failed && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6 text-center">
              <p className="muted">{t("drop")}</p>
            </div>
          )}
          {loading && <div className="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-black/40"><p role="status">{t("loading")}</p></div>}
          {failed && <p role="alert" className="absolute inset-0 flex items-center justify-center p-6 text-center">{t("noWebgl")}</p>}
        </div>
        <aside className="flex flex-col gap-4" aria-label={t("tools")}>
          {model && size && (
            <section className="card flex flex-col gap-1 p-4 text-sm" data-visor-info>
              <h2 className="mb-1 font-semibold">{model.name}</h2>
              <p>{t("size")}: <span data-visor-size>{formatMm(size.x, locale)} × {formatMm(size.z, locale)} × {formatMm(size.y, locale)}</span></p>
              <p className="muted text-xs">{t("sizeHelp")}</p>
              {model.points ? <p>{t("points", { n: model.points.toLocaleString(locale) })}</p>
                : <p>{t("triangles", { n: model.triangles.toLocaleString(locale) })}</p>}
              <p>{t("parts", { n: model.meshes })}</p>
              {distance !== null && <p className="font-semibold" data-visor-distance>{t("distance", { value: formatMm(distance, locale) })}</p>}
              {model.warnings.map((w) => <p key={w} className="text-amber-700 dark:text-amber-300">{w}</p>)}
            </section>
          )}
          <section className="card flex flex-col gap-3 p-4 text-sm">
            <div>
              <h2 className="mb-2 font-semibold">{t("views")}</h2>
              <div className="flex flex-wrap gap-2">
                {ANGLES.map((a) => <button key={a} type="button" className="btn-secondary btn" disabled={!model} onClick={() => setAngle(a)}>{t(`angle.${a}`)}</button>)}
              </div>
            </div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={wireframe} onChange={(e) => setWireframe(e.target.checked)} />{t("wireframe")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={grid} onChange={(e) => setGrid(e.target.checked)} />{t("grid")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={showBox} onChange={(e) => setShowBox(e.target.checked)} />{t("box")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={measuring} disabled={!model} onChange={(e) => setMeasuring(e.target.checked)} data-visor-measure />{t("measure")}</label>
            {measuring && <p className="muted text-xs">{t("measureHelp")}</p>}
            <label className="flex flex-col gap-1">
              <span>{t("section")}</span>
              <select className="input" value={section} disabled={!model} onChange={(e) => setSection(e.target.value as Axis | "")} data-visor-section>
                <option value="">{t("sectionOff")}</option>
                <option value="x">{t("sectionAxis", { axis: "X" })}</option>
                <option value="z">{t("sectionAxis", { axis: "Y" })}</option>
                <option value="y">{t("sectionAxis", { axis: "Z" })}</option>
              </select>
            </label>
            {section && (
              <label className="flex flex-col gap-1">
                <span>{t("sectionAt", { pct: sectionAt })}</span>
                <input type="range" min={0} max={100} value={sectionAt} onChange={(e) => setSectionAt(Number(e.target.value))} />
              </label>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={Boolean(color)} disabled={!model} onChange={(e) => setColor(e.target.checked ? "#e67610" : "")} />{t("color")}
              </label>
              {color && <input type="color" aria-label={t("color")} value={color} onChange={(e) => setColor(e.target.value)} />}
            </div>
            <label className="flex flex-col gap-1">
              <span>{t("up")}</span>
              <select className="input" value={up} onChange={(e) => setUp(e.target.value as "auto" | "y" | "z")}>
                <option value="auto">{t("upAuto")}</option>
                <option value="z">{t("upZ")}</option>
                <option value="y">{t("upY")}</option>
              </select>
            </label>
            <button type="button" className="btn" disabled={!model} onClick={() => void capture()} data-visor-capture>{t("capture")}</button>
          </section>
          <p className="muted text-xs">{t("privacy")}</p>
        </aside>
      </div>
      <div aria-live="polite" className="sr-only">{status}</div>
      {error && <p role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300" data-visor-error>{error}</p>}
    </div>
  );
}
