// Google Drive y Dropbox (8.2.4): solo con su flag y sus claves públicas; ninguna credencial pasa por el servidor.
export interface CloudConfig {
  gdrive: { clientId: string; apiKey: string } | null;
  dropbox: { appKey: string } | null;
}

function on(name: string): boolean {
  return ["1", "true", "yes", "si", "sí", "on"].includes((process.env[name] ?? "").toLowerCase());
}

export function cloudConfig(): CloudConfig {
  const clientId = process.env.GOOGLE_PICKER_CLIENT_ID ?? "";
  const apiKey = process.env.GOOGLE_PICKER_API_KEY ?? "";
  const appKey = process.env.DROPBOX_APP_KEY ?? "";
  return {
    gdrive: on("GDRIVE_ENABLED") && clientId && apiKey ? { clientId, apiKey } : null,
    dropbox: on("DROPBOX_ENABLED") && appKey ? { appKey } : null,
  };
}

/** Orígenes que la CSP añade cuando cada servicio está activo. */
export const CLOUD_CSP = {
  gdrive: {
    script: ["https://accounts.google.com", "https://apis.google.com"],
    connect: ["https://www.googleapis.com", "https://content.googleapis.com"],
    frame: ["https://accounts.google.com", "https://docs.google.com", "https://content.googleapis.com"],
  },
  dropbox: {
    script: ["https://www.dropbox.com"],
    connect: ["https://dl.dropboxusercontent.com"],
    frame: ["https://www.dropbox.com"],
  },
} as const;
