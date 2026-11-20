"use client";

// firmar-pdf (A.6, F4-B2a): panel del editor. «Insertar firma» se queda en el navegador; «Firmar digitalmente» sube el
// PDF (con la firma insertada, si la hay) a la ruta de servidor, donde `workersign` pone el sello de la plataforma
// (PAdES, D-188), dentro de un campo de firma vacío del PDF si se elige uno (hacer-pdf-rellenable, D-196).
import { parsePageRanges, type FormInfo } from "@conversor/client-tools";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import type { OwnCertificate } from "@/lib/p12";
import { identityToken } from "@/lib/identity";
import { getConfig } from "@/lib/runtime";
import { runServerJob } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";
import { SignatureDialog, toPngDataUrl } from "./SignatureDialog";

export interface DigitalOptions {
  certificado: "plataforma" | "propio";
  /** Certificado propio abierto en el navegador (D-199): su clave nunca se envía. */
  own?: OwnCertificate;
  visible: boolean;
  pagina: string;
  posicion: "abajo_derecha" | "abajo_izquierda" | "arriba_derecha" | "arriba_izquierda";
  campo: string;
  nombre: string;
  motivo: string;
  lugar: string;
  sello_tiempo: boolean;
  nivel: "B-T" | "B-LT" | "B-LTA";
  certificacion: "no" | "sin_cambios" | "formularios" | "formularios_anotaciones";
  /** Firma dibujada, escrita o subida dentro de la apariencia del sello (PNG en data URL; D-210). */
  imagen?: string;
}

const DEFAULTS: DigitalOptions = {
  certificado: "plataforma", visible: true, pagina: "ultima", posicion: "abajo_derecha", campo: "", nombre: "", motivo: "", lugar: "",
  sello_tiempo: true, nivel: "B-T", certificacion: "no",
};
const TURNSTILE_BOX = "firma-turnstile";

async function job(file: File, options: Record<string, unknown>, token: string, onProgress: (f: number) => void) {
  const done = await runServerJob("firmar-pdf", [file], options, token,
    (phase) => onProgress(phase.kind === "upload" ? phase.percent / 200 : phase.kind === "running" ? 0.5 + phase.progress / 2 : 0.5),
    new AbortController().signal);
  if (done.status !== "succeeded") throw new ApiError(done.error?.code ?? "INTERNAL", done.error?.message ?? "", 0);
  return done.outputs;
}

/**
 * Firma digital desde la página. Con el sello de la plataforma, un trabajo. Con el certificado propio (firma
 * interrumpida, D-199), dos: «preparar» devuelve el PDF con el hueco y los atributos de CMS, el navegador los firma con
 * WebCrypto y «completar» escribe la firma, el sello de tiempo y los datos de validación.
 */
export async function signDigitally(file: File, options: DigitalOptions, locale: string, onProgress: (f: number) => void) {
  const config = await getConfig();
  const token = await identityToken(async () => {
    const box = document.getElementById(TURNSTILE_BOX);
    if (!box) throw new ApiError("TURNSTILE_FAILED", "", 403);
    return solveTurnstile(box as HTMLDivElement, config.turnstileSiteKey, locale);
  });
  const { own, ...rest } = options;
  let outputs;
  if (rest.certificado === "propio") {
    if (!own) throw new ApiError("INVALID_OPTIONS", "", 0);
    const { checkAttributes, signAttributes } = await import("@/lib/p12");
    const base = { ...rest, cadena: own.chainPem };
    const first = await job(file, { ...base, fase: "preparar" }, token, (f) => onProgress(f / 2));
    const preparedOut = first.find((o) => o.name.toLowerCase().endsWith(".pdf"));
    const stateOut = first.find((o) => o.name.toLowerCase().endsWith(".json"));
    if (!preparedOut || !stateOut) throw new ApiError("INTERNAL", "", 0);
    const [pdfRes, stateRes] = await Promise.all([fetch(preparedOut.url), fetch(stateOut.url)]);
    if (!pdfRes.ok || !stateRes.ok) throw new ApiError("INTERNAL", "", pdfRes.ok ? stateRes.status : pdfRes.status);
    const [prepared, stateText] = await Promise.all([pdfRes.blob(), stateRes.text()]);
    const state = JSON.parse(stateText) as { attrs: string; start: number; end: number };
    // La clave solo firma si los atributos son los de este PDF y este certificado (D-201).
    await checkAttributes(own, state.attrs, new Uint8Array(await prepared.arrayBuffer()), state.start, state.end);
    const firma = await signAttributes(own, state.attrs);
    outputs = await job(new File([prepared], preparedOut.name, { type: "application/pdf" }), { ...base, fase: "completar", estado: stateText, firma },
      token, (f) => onProgress(0.5 + f / 2));
  } else {
    outputs = await job(file, rest, token, onProgress);
  }
  const pdf = outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
  if (!pdf) throw new ApiError("INTERNAL", "", 0);
  return { url: pdf.url, name: pdf.name, size: pdf.size, notes: pdf.note ? [pdf.note] : [] };
}

export function SignPanel({ form, pageCount, selected, onRepeat, onDigital }: {
  form: FormInfo | null; pageCount: number; selected: { page: number } | null;
  onRepeat: (pages: number[]) => void; onDigital: (options: DigitalOptions | null) => void;
}) {
  const t = useTranslations("signPdf");
  const [drawingSeal, setDrawingSeal] = useState(false);
  const [mode, setMode] = useState<"insertar" | "digital">("insertar");
  const [options, setOptions] = useState<DigitalOptions>(DEFAULTS);
  const [repeat, setRepeat] = useState("todas");
  const [p12, setP12] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [p12Error, setP12Error] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  async function openCertificate() {
    if (!p12) return;
    setP12Error(null);
    setOpening(true);
    try {
      const { openP12 } = await import("@/lib/p12");
      const own = await openP12(await p12.arrayBuffer(), password);
      setPassword("");
      setOptions((o) => ({ ...o, own }));
    } catch (err) {
      const code = (err as { code?: string }).code ?? "p12_invalid";
      setP12Error(t.has(code) ? t(code) : t("p12_invalid"));
    } finally {
      setOpening(false);
    }
  }
  const fields = (form?.fields ?? []).filter((f) => f.type === "signature" && !f.signed).map((f) => f.name);

  useEffect(() => {
    onDigital(mode === "digital" ? options : null);
  }, [mode, options, onDigital]);

  const set = (change: Partial<DigitalOptions>) => setOptions((o) => ({ ...o, ...change }));
  // parsePageRanges lanza con un rango mal escrito: aquí no puede romper el editor (D-201).
  let targets: number[] = [];
  let repeatError = false;
  try {
    targets = parsePageRanges(repeat, pageCount);
  } catch {
    repeatError = true;
  }

  return (
    <aside className="flex flex-col gap-3 text-sm lg:sticky lg:top-32 lg:max-h-[80vh] lg:w-80 lg:self-start lg:overflow-y-auto" aria-label={t("panel")}>
      {form?.signed && <p className="card p-3" role="alert">{t("alreadySigned")}</p>}
      <fieldset className="card flex flex-col gap-2 p-3">
        <legend className="font-semibold">{t("mode")}</legend>
        <label className="flex items-center gap-2"><input type="radio" name="modo-firma" checked={mode === "insertar"} onChange={() => setMode("insertar")} />{t("insert")}</label>
        <label className="flex items-center gap-2"><input type="radio" name="modo-firma" checked={mode === "digital"} onChange={() => setMode("digital")} />{t("digital")}</label>
        <p className="muted">{t(mode === "insertar" ? "insertHint" : "digitalHint")}</p>
      </fieldset>

      <div className="card flex flex-col gap-2 p-3" role="group" aria-label={t("repeat")}>
        <p className="font-semibold">{t("repeat")}</p>
        <label className="flex flex-col gap-1">{t("repeatPages")}
          <input className="field" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
        </label>
        <button type="button" className="btn-secondary btn self-start" disabled={!selected || !targets.length} onClick={() => onRepeat(targets)}>
          {t("repeatButton")}
        </button>
        {repeatError && <p role="alert" className="text-red-700">{t("repeatInvalid", { n: pageCount })}</p>}
        {!selected && <p className="muted">{t("repeatHint")}</p>}
      </div>

      {mode === "digital" && (
        <div className="card flex flex-col gap-2 p-3" role="group" aria-label={t("digital")}>
          <label className="flex flex-col gap-1">{t("certificate")}
            <select className="field" value={options.certificado} onChange={(e) => set({ certificado: e.target.value as DigitalOptions["certificado"] })}>
              <option value="plataforma">{t("platformSeal")}</option>
              <option value="propio">{t("ownCertificate")}</option>
            </select>
          </label>
          {options.certificado === "propio" && (
            <div className="flex flex-col gap-2 rounded border p-2">
              {options.own ? (
                <>
                  <p>{t("ownOpened", { subject: options.own.subject, date: options.own.notAfter.toLocaleDateString() })}</p>
                  <button type="button" className="btn-secondary btn self-start" onClick={() => { set({ own: undefined }); setP12(null); }}>{t("ownChange")}</button>
                </>
              ) : (
                <>
                  <label className="flex flex-col gap-1">{t("ownFile")}
                    <input className="field" type="file" accept=".p12,.pfx" onChange={(e) => setP12(e.target.files?.[0] ?? null)} />
                  </label>
                  <label className="flex flex-col gap-1">{t("ownPassword")}
                    <input className="field" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
                  </label>
                  <button type="button" className="btn-secondary btn self-start" disabled={!p12 || opening} onClick={() => void openCertificate()}>
                    {opening ? t("ownOpening") : t("ownOpen")}
                  </button>
                  {p12Error && <p role="alert" className="text-red-700">{p12Error}</p>}
                </>
              )}
              <p className="muted">{t("ownPrivacy")}</p>
            </div>
          )}
          {fields.length > 0 && (
            <label className="flex flex-col gap-1">{t("field")}
              <select className="field" value={options.campo} onChange={(e) => set({ campo: e.target.value })}>
                <option value="">{t("newField")}</option>
                {fields.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
          )}
          {!options.campo && (
            <>
              <label className="flex items-center gap-2"><input type="checkbox" checked={options.visible} onChange={(e) => set({ visible: e.target.checked })} />{t("visible")}</label>
              {options.visible && (
                <>
                  <label className="flex flex-col gap-1">{t("page")}
                    <input className="field" value={options.pagina} maxLength={10} onChange={(e) => set({ pagina: e.target.value })} />
                  </label>
                  <label className="flex flex-col gap-1">{t("position")}
                    <select className="field" value={options.posicion} onChange={(e) => set({ posicion: e.target.value as DigitalOptions["posicion"] })}>
                      {(["abajo_derecha", "abajo_izquierda", "arriba_derecha", "arriba_izquierda"] as const).map((p) => <option key={p} value={p}>{t(`pos_${p}`)}</option>)}
                    </select>
                  </label>
                </>
              )}
            </>
          )}
          {(options.visible || options.campo) && (
            <div className="flex flex-col gap-1" data-seal-image>
              <span>{t("sealImage")}</span>
              {options.imagen && <img src={options.imagen} alt={t("sealImagePreview")} className="max-h-16 w-auto self-start rounded border bg-white p-1" />}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-secondary btn" onClick={() => setDrawingSeal(true)}>{options.imagen ? t("sealImageChange") : t("sealImageAdd")}</button>
                {options.imagen && <button type="button" className="btn-secondary btn" onClick={() => set({ imagen: undefined })}>{t("sealImageRemove")}</button>}
              </div>
            </div>
          )}
          {drawingSeal && (
            <SignatureDialog onCancel={() => setDrawingSeal(false)} onDone={(img) => {
              setDrawingSeal(false);
              void toPngDataUrl(img, 800, 300).then((imagen) => set({ imagen }));
            }} />
          )}
          <label className="flex flex-col gap-1">{t("name")}
            <input className="field" value={options.nombre} maxLength={120} onChange={(e) => set({ nombre: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">{t("reason")}
            <input className="field" value={options.motivo} maxLength={200} onChange={(e) => set({ motivo: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">{t("location")}
            <input className="field" value={options.lugar} maxLength={120} onChange={(e) => set({ lugar: e.target.value })} />
          </label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={options.sello_tiempo} onChange={(e) => set({ sello_tiempo: e.target.checked })} />{t("timestamp")}</label>
          {options.sello_tiempo && (
            <label className="flex flex-col gap-1">{t("level")}
              <select className="field" value={options.nivel} onChange={(e) => set({ nivel: e.target.value as DigitalOptions["nivel"] })}>
                <option value="B-T">PAdES B-T</option>
                <option value="B-LT">PAdES B-LT</option>
                <option value="B-LTA">PAdES B-LTA</option>
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1">{t("certification")}
            <select className="field" value={options.certificacion} onChange={(e) => set({ certificacion: e.target.value as DigitalOptions["certificacion"] })}>
              {(["no", "sin_cambios", "formularios", "formularios_anotaciones"] as const).map((c) => <option key={c} value={c}>{t(`cert_${c}`)}</option>)}
            </select>
          </label>
          {options.certificado === "plataforma" && <p className="muted">{t("accountNeeded")}</p>}
          <div id={TURNSTILE_BOX} aria-live="polite" />
        </div>
      )}
    </aside>
  );
}
