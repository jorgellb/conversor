"use client";

// Botones de Google Drive y Dropbox (8.2.4): solo aparecen con su flag activo y sus claves configuradas.
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { chooseFromDropbox, pickFromDrive, saveToDrive, saveToDropbox } from "@/lib/cloud";
import { getConfig, type RuntimeConfig } from "@/lib/runtime";

function useCloud(): Pick<RuntimeConfig, "gdrive" | "dropbox"> {
  const [cfg, setCfg] = useState<Pick<RuntimeConfig, "gdrive" | "dropbox">>({ gdrive: null, dropbox: null });
  useEffect(() => {
    void getConfig().then((c) => setCfg({ gdrive: c.gdrive ?? null, dropbox: c.dropbox ?? null })).catch(() => undefined);
  }, []);
  return cfg;
}

export function CloudOpen({ accept, multiple, onFiles }: { accept: string[]; multiple: boolean; onFiles: (files: File[]) => void }) {
  const t = useTranslations("cloud");
  const { gdrive, dropbox } = useCloud();
  const [error, setError] = useState<string | null>(null);
  if (!gdrive && !dropbox) return null;
  const run = async (service: string, fn: () => Promise<File[]>) => {
    setError(null);
    try {
      const files = await fn();
      if (files.length) onFiles(files);
    } catch {
      setError(t("error", { service }));
    }
  };
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {gdrive && <button type="button" className="btn-secondary btn" onClick={() => void run("Google Drive", () => pickFromDrive(gdrive, multiple))}>{t("openDrive")}</button>}
      {dropbox && <button type="button" className="btn-secondary btn" onClick={() => void run("Dropbox", () => chooseFromDropbox(dropbox.appKey, accept, multiple))}>{t("openDropbox")}</button>}
      {error && <p role="alert" className="w-full text-sm text-red-700">{error}</p>}
    </div>
  );
}

export function CloudSave({ url, name, local }: { url: string; name: string; local: boolean }) {
  const t = useTranslations("cloud");
  const { gdrive, dropbox } = useCloud();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  if (!gdrive && !dropbox) return null;
  const run = async (service: string, fn: () => Promise<boolean | void>) => {
    setMessage(null);
    try {
      if ((await fn()) !== false) setMessage({ ok: true, text: t("saved", { service }) });
    } catch {
      setMessage({ ok: false, text: t("error", { service }) });
    }
  };
  return (
    <span className="flex flex-wrap items-center gap-2">
      {gdrive && (
        <button type="button" className="btn-secondary btn" onClick={() => void run("Google Drive", async () => saveToDrive(gdrive, await (await fetch(url)).blob(), name))}>
          {t("saveDrive")}
        </button>
      )}
      {/* Dropbox descarga el archivo desde sus servidores: solo con resultados del servidor (URL firmada de 15 minutos). */}
      {dropbox && !local && (
        <button type="button" className="btn-secondary btn" onClick={() => void run("Dropbox", () => saveToDropbox(dropbox.appKey, url, name))}>{t("saveDropbox")}</button>
      )}
      {message && <span role={message.ok ? "status" : "alert"} className={message.ok ? "text-sm" : "text-sm text-red-700"}>{message.text}</span>}
    </span>
  );
}
