"use client";

// firmar-pdf (A.6, F4-B2a): panel del editor. «Insertar firma» se queda en el navegador; «Firmar digitalmente» sube el
// PDF (con la firma insertada, si la hay) a la ruta de servidor, donde `workersign` pone el sello de la plataforma
// (PAdES, D-188), dentro de un campo de firma vacío del PDF si se elige uno (hacer-pdf-rellenable, D-196).
import { parsePageRanges, type FormInfo } from "@conversor/client-tools";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { identityToken } from "@/lib/identity";
import { getConfig } from "@/lib/runtime";
import { runServerJob } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";

export interface DigitalOptions {
  certificado: "plataforma";
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
}

const DEFAULTS: DigitalOptions = {
  certificado: "plataforma", visible: true, pagina: "ultima", posicion: "abajo_derecha", campo: "", nombre: "", motivo: "", lugar: "",
  sello_tiempo: true, nivel: "B-T", certificacion: "no",
};
const TURNSTILE_BOX = "firma-turnstile";

/** Sube el PDF a firmar-pdf con el sello de la plataforma y devuelve el enlace de descarga. */
export async function signDigitally(file: File, options: DigitalOptions, locale: string, onProgress: (f: number) => void) {
  const config = await getConfig();
  const token = await identityToken(async () => {
    const box = document.getElementById(TURNSTILE_BOX);
    if (!box) throw new ApiError("TURNSTILE_FAILED", "", 403);
    return solveTurnstile(box as HTMLDivElement, config.turnstileSiteKey, locale);
  });
  const job = await runServerJob("firmar-pdf", [file], { ...options }, token,
    (phase) => onProgress(phase.kind === "upload" ? phase.percent / 200 : phase.kind === "running" ? 0.5 + phase.progress / 2 : 0.5),
    new AbortController().signal);
  if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
  const pdf = job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
  if (!pdf) throw new ApiError("INTERNAL", "", 0);
  return { url: pdf.url, name: pdf.name, size: pdf.size, notes: pdf.note ? [pdf.note] : [] };
}

export function SignPanel({ form, pageCount, selected, onRepeat, onDigital }: {
  form: FormInfo | null; pageCount: number; selected: { page: number } | null;
  onRepeat: (pages: number[]) => void; onDigital: (options: DigitalOptions | null) => void;
}) {
  const t = useTranslations("signPdf");
  const [mode, setMode] = useState<"insertar" | "digital">("insertar");
  const [options, setOptions] = useState<DigitalOptions>(DEFAULTS);
  const [repeat, setRepeat] = useState("todas");
  const fields = (form?.fields ?? []).filter((f) => f.type === "signature").map((f) => f.name);

  useEffect(() => {
    onDigital(mode === "digital" ? options : null);
  }, [mode, options, onDigital]);

  const set = (change: Partial<DigitalOptions>) => setOptions((o) => ({ ...o, ...change }));
  const targets = parsePageRanges(repeat, pageCount);

  return (
    <aside className="flex flex-col gap-3 text-sm lg:sticky lg:top-32 lg:max-h-[80vh] lg:w-80 lg:self-start lg:overflow-y-auto" aria-label={t("panel")}>
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
        {!selected && <p className="muted">{t("repeatHint")}</p>}
      </div>

      {mode === "digital" && (
        <div className="card flex flex-col gap-2 p-3" role="group" aria-label={t("digital")}>
          <label className="flex flex-col gap-1">{t("certificate")}
            <select className="field" value={options.certificado} onChange={() => set({ certificado: "plataforma" })}>
              <option value="plataforma">{t("platformSeal")}</option>
            </select>
          </label>
          <p className="muted">{t("ownCertificateSoon")}</p>
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
          <p className="muted">{t("accountNeeded")}</p>
          <div id={TURNSTILE_BOX} aria-live="polite" />
        </div>
      )}
    </aside>
  );
}
