"use client";

// Página del firmante de solicitar-firmas (7.7, F4-C2, D-202): sin cuenta, con el enlace del correo. El token va en el
// fragmento (#…), que el navegador no manda al servidor web; solo viaja a la API en la ruta de /v1/sign/{token}.
// Pasos: ver el documento, pedir el código al correo, dibujar o escribir la firma, aceptar y firmar (o rechazar).
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { getConfig } from "@/lib/runtime";

import { SignatureDialog, type PreparedImage } from "../editor/SignatureDialog";
import { solveTurnstile } from "../turnstile";

interface SignView {
  request: { document_name: string; owner_email: string; message: string; status: string; sequential: boolean; expires_at: string | null; locale: string };
  signer: { name: string; email: string; status: string; signed_at: string | null; can_sign: boolean; code_sent: boolean };
  signers: { name: string; status: string; me: boolean }[];
  consent: string;
  document_url: string | null;
  files: { name: string; url: string }[];
}

/** La firma en PNG y de un tamaño razonable (la API admite hasta 2000 × 1000 y 400 KB). */
async function toPng(img: PreparedImage): Promise<string> {
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(img.data)], { type: img.format === "png" ? "image/png" : "image/jpeg" }));
  const scale = Math.min(1, 1200 / bitmap.width, 500 / bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(20, Math.round(bitmap.width * scale));
  canvas.height = Math.max(10, Math.round(bitmap.height * scale));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/png");
}

export function SignerPage() {
  const t = useTranslations("signerPage");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [view, setView] = useState<SignView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [image, setImage] = useState<{ url: string; data: string } | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [consent, setConsent] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const box = useRef<HTMLDivElement>(null);

  const message = (err: unknown) => {
    const code = err instanceof ApiError ? err.code : "INTERNAL";
    return err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL");
  };

  const load = useCallback(async (tk: string) => {
    try {
      setView(await api<SignView>(`/v1/sign/${tk}`));
      setError(null);
    } catch (err) {
      setView(null);
      setError(message(err));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const tk = window.location.hash.replace(/^#/, "").trim();
    setToken(tk || null);
    if (tk) void load(tk);
  }, [load]);

  // Mientras se sella su firma o la final, la página se actualiza sola.
  useEffect(() => {
    if (!token || !view) return;
    const waiting = ["queued", "signing"].includes(view.signer.status) || view.request.status === "finalizing";
    if (!waiting) return;
    const timer = window.setInterval(() => void load(token), 4000);
    return () => window.clearInterval(timer);
  }, [token, view, load]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  const sendCode = () => run(async () => {
    const config = await getConfig();
    if (!box.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
    const turnstile = await solveTurnstile(box.current, config.turnstileSiteKey, locale);
    await api(`/v1/sign/${token}/code`, { method: "POST", body: { turnstile_token: turnstile } });
    await load(token!);
  });

  const sign = () => run(async () => {
    if (!image) throw new ApiError("INVALID_OPTIONS", t("needSignature"), 0);
    setView(await api<SignView>(`/v1/sign/${token}`, { method: "POST", body: { code: code.trim(), image: image.data, consent: true } }));
    setCode("");
  });

  const decline = () => run(async () => {
    setView(await api<SignView>(`/v1/sign/${token}/decline`, { method: "POST", body: { code: code.trim(), reason: reason.trim() } }));
    setDeclining(false);
  });

  async function openDocument() {
    if (!view?.document_url) return;
    await run(async () => {
      const res = await fetch(view.document_url!);
      if (!res.ok) throw new ApiError("NOT_FOUND", "", res.status);
      const url = URL.createObjectURL(new Blob([await res.blob()], { type: "application/pdf" }));
      window.open(url, "_blank", "noopener");
    });
  }

  if (token === undefined) return <p className="muted">{t("loading")}</p>;
  if (token === null) return <p className="card p-4" role="alert">{t("noToken")}</p>;
  if (!view) return error ? <p className="card p-4" role="alert">{error}</p> : <p className="muted">{t("loading")}</p>;

  const r = view.request;
  const s = view.signer;
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(locale === "en" ? "en-GB" : "es-ES", { dateStyle: "medium", timeStyle: "short" }) : "");
  const closed = ["declined", "cancelled", "expired", "failed"].includes(r.status);

  return (
    <div className="flex flex-col gap-5" data-request-status={r.status} data-signer-status={s.status}>
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <section className="card flex flex-col gap-2 p-4">
        <p className="text-lg font-semibold">{r.document_name}</p>
        <p>{t("from", { owner: r.owner_email, name: s.name })}</p>
        {r.message && <blockquote className="border-l-4 pl-3 italic">{r.message}</blockquote>}
        {!closed && r.status !== "completed" && <p className="muted text-sm">{t("until", { date: when(r.expires_at) })}</p>}
        <ol className="mt-1 flex flex-col gap-0.5 text-sm">
          {view.signers.map((x, i) => (
            <li key={i}>{x.name}{x.me ? ` (${t("you")})` : ""} — {t(`signer.${x.status}`)}</li>
          ))}
        </ol>
        {view.document_url && (
          <div><button type="button" className="btn-secondary btn" onClick={() => void openDocument()} disabled={busy}>{t("open")}</button></div>
        )}
      </section>

      {closed && <p className="card p-4" role="status">{t(`closed.${r.status}`)}</p>}

      {r.status === "completed" && (
        <section className="card flex flex-col gap-2 p-4" role="status">
          <p>{t("completed")}</p>
          <div className="flex flex-wrap gap-2">
            {view.files.map((f) => <a key={f.name} className="btn" href={f.url} download>{f.name}</a>)}
          </div>
        </section>
      )}

      {!closed && r.status !== "completed" && s.status === "signed" && <p className="card p-4" role="status">{t("signedWaiting")}</p>}
      {["queued", "signing"].includes(s.status) && <p className="card p-4" role="status">{t("sealing")}</p>}
      {!closed && s.status === "waiting" && <p className="card p-4">{t("notYourTurn")}</p>}

      {s.can_sign && (
        <section className="card flex flex-col gap-4 p-4" aria-label={t("signTitle")}>
          <h2 className="text-xl font-semibold">{t("signTitle")}</h2>
          <div className="flex flex-col gap-2">
            <p>{t("step1", { email: s.email })}</p>
            <div><button type="button" className="btn-secondary btn" disabled={busy} onClick={() => void sendCode()}>
              {s.code_sent ? t("resend") : t("sendCode")}
            </button></div>
            {s.code_sent && <p className="muted text-sm">{t("codeSent")}</p>}
          </div>
          <label className="flex flex-col gap-1">{t("code")}
            {/* Sin maxLength: al pegar «123 456» se quitan primero los espacios y luego se corta a 6 cifras. */}
            <input className="field w-40 font-mono tracking-widest" inputMode="numeric" autoComplete="one-time-code"
                   value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          </label>
          <div className="flex flex-col gap-2">
            <p>{t("step2")}</p>
            {image && <img src={image.url} alt={t("preview")} className="max-h-28 w-auto self-start rounded border bg-white p-2" />}
            <div><button type="button" className="btn-secondary btn" onClick={() => setDrawing(true)}>{image ? t("redo") : t("draw")}</button></div>
          </div>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>{view.consent}</span>
          </label>
          <p className="muted text-sm">{t("legal")}</p>
          <div ref={box} aria-live="polite" />
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn" disabled={busy || code.length !== 6 || !image || !consent} onClick={() => void sign()}>{t("sign")}</button>
            <button type="button" className="btn-secondary btn" disabled={busy} onClick={() => setDeclining((v) => !v)}>{t("decline")}</button>
          </div>
          {declining && (
            <div className="flex flex-col gap-2">
              <label className="flex flex-col gap-1 text-sm">{t("reason")}
                <textarea className="field" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <p className="muted text-sm">{t("declineCode")}</p>
              <div><button type="button" className="btn-secondary btn" disabled={busy || code.length !== 6} onClick={() => void decline()}>{t("confirmDecline")}</button></div>
            </div>
          )}
        </section>
      )}

      {error && <p role="alert" className="text-red-700">{error}</p>}

      {drawing && (
        <SignatureDialog onCancel={() => setDrawing(false)} onDone={(img) => {
          setDrawing(false);
          void toPng(img).then((data) => setImage({ url: img.url, data }));
        }} />
      )}
    </div>
  );
}
