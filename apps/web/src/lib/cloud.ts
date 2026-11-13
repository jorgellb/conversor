"use client";

// Abrir desde y guardar en Google Drive y Dropbox (8.2.4). Los scripts de terceros se cargan al pulsar el botón.
/* eslint-disable @typescript-eslint/no-explicit-any */
import type { RuntimeConfig } from "./runtime";

declare global {
  interface Window {
    google?: any;
    gapi?: any;
    Dropbox?: any;
  }
}

const scripts = new Map<string, Promise<void>>();

function loadScript(src: string, attrs: Record<string, string> = {}): Promise<void> {
  if (!scripts.has(src)) {
    scripts.set(src, new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.async = true;
      for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
      el.onload = () => resolve();
      el.onerror = () => {
        scripts.delete(src);
        reject(new Error(`No se pudo cargar ${src}`));
      };
      document.head.appendChild(el);
    }));
  }
  return scripts.get(src)!;
}

type Drive = NonNullable<RuntimeConfig["gdrive"]>;

/** Token de acceso con el ámbito `drive.file`: solo los archivos que la persona elige o que crea esta web. */
async function driveToken(cfg: Drive): Promise<string> {
  await loadScript("https://accounts.google.com/gsi/client");
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: cfg.clientId,
      scope: "https://www.googleapis.com/auth/drive.file",
      callback: (res: { access_token?: string; error?: string }) => (res.access_token ? resolve(res.access_token) : reject(new Error(res.error ?? "token"))),
      error_callback: (err: { type?: string }) => reject(new Error(err?.type ?? "popup")),
    });
    client.requestAccessToken();
  });
}

export async function pickFromDrive(cfg: Drive, multiple: boolean): Promise<File[]> {
  const token = await driveToken(cfg);
  await loadScript("https://apis.google.com/js/api.js");
  await new Promise<void>((resolve) => window.gapi.load("picker", () => resolve()));
  const g = window.google.picker;
  const docs = await new Promise<{ id: string; name: string; mimeType: string }[]>((resolve) => {
    const view = new g.DocsView(g.ViewId.DOCS).setIncludeFolders(false).setSelectFolderEnabled(false);
    const builder = new g.PickerBuilder().addView(view).setOAuthToken(token).setDeveloperKey(cfg.apiKey)
      .setCallback((data: { action: string; docs?: { id: string; name: string; mimeType: string }[] }) => {
        if (data.action === g.Action.PICKED) resolve(data.docs ?? []);
        else if (data.action === g.Action.CANCEL) resolve([]);
      });
    if (multiple) builder.enableFeature(g.Feature.MULTISELECT_ENABLED);
    builder.build().setVisible(true);
  });
  return Promise.all(docs.map(async (d) => {
    const res = await fetch(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(d.id)}?alt=media`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Drive ${res.status}`);
    return new File([await res.blob()], d.name, { type: d.mimeType });
  }));
}

export async function saveToDrive(cfg: Drive, blob: Blob, name: string): Promise<void> {
  const token = await driveToken(cfg);
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify({ name })], { type: "application/json" }));
  form.append("file", blob, name);
  const res = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id", {
    method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
  });
  if (!res.ok) throw new Error(`Drive ${res.status}`);
}

async function dropbox(appKey: string): Promise<any> {
  await loadScript("https://www.dropbox.com/static/api/2/dropins.js", { id: "dropboxjs", "data-app-key": appKey });
  return window.Dropbox;
}

export async function chooseFromDropbox(appKey: string, extensions: string[], multiple: boolean): Promise<File[]> {
  const box = await dropbox(appKey);
  const files = await new Promise<{ link: string; name: string }[]>((resolve) => box.choose({
    linkType: "direct", multiselect: multiple, folderselect: false, extensions: extensions.map((e) => `.${e}`),
    success: resolve, cancel: () => resolve([]),
  }));
  return Promise.all(files.map(async (f) => {
    const res = await fetch(f.link);
    if (!res.ok) throw new Error(`Dropbox ${res.status}`);
    return new File([await res.blob()], f.name);
  }));
}

/** Dropbox Saver: son sus servidores los que descargan la URL firmada (15 minutos). */
export async function saveToDropbox(appKey: string, url: string, name: string): Promise<boolean> {
  const box = await dropbox(appKey);
  return new Promise((resolve, reject) => box.save(url, name, {
    success: () => resolve(true), cancel: () => resolve(false), error: (msg: string) => reject(new Error(msg)),
  }));
}
