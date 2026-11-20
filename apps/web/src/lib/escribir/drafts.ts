// escribir-pdf (A.1, F6-O1, D-234): borrador y versiones en IndexedDB del navegador. Nada se guarda en el servidor,
// coherente con la política de retención (la sincronización con la cuenta queda como mejora en docs/TOOLS.md).
// Si IndexedDB no está disponible (ventana privada, almacenamiento bloqueado), el editor funciona sin guardar.
import type { PMNode } from "./model";

const DB = "escribir-pdf";
const STORE = "documentos";
const DRAFT = "borrador";
export const MAX_VERSIONS = 20;

export interface SavedDoc {
  id: string;
  title: string;
  savedAt: number;
  doc: PMNode;
  page: Record<string, unknown>;
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("indexeddb"));
      return;
    }
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("indexeddb"));
  });
}

async function withStore<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await open();
  try {
    return await new Promise<T | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req ? req.result : undefined);
      tx.onerror = () => reject(tx.error ?? new Error("indexeddb"));
      tx.onabort = () => reject(tx.error ?? new Error("indexeddb"));
    });
  } finally {
    db.close();
  }
}

export async function saveDraft(doc: PMNode, page: Record<string, unknown>, title: string): Promise<boolean> {
  try {
    await withStore("readwrite", (s) => s.put({ id: DRAFT, title, savedAt: Date.now(), doc, page } satisfies SavedDoc));
    return true;
  } catch {
    return false;
  }
}

export async function loadDraft(): Promise<SavedDoc | null> {
  try {
    return ((await withStore<SavedDoc>("readonly", (s) => s.get(DRAFT))) as SavedDoc | undefined) ?? null;
  } catch {
    return null;
  }
}

export async function listVersions(): Promise<SavedDoc[]> {
  try {
    const all = ((await withStore<SavedDoc[]>("readonly", (s) => s.getAll())) as SavedDoc[] | undefined) ?? [];
    return all.filter((d) => d.id !== DRAFT).sort((a, b) => b.savedAt - a.savedAt);
  } catch {
    return [];
  }
}

/** Guarda una versión con nombre; si pasan de MAX_VERSIONS, se borran las más antiguas. */
export async function saveVersion(doc: PMNode, page: Record<string, unknown>, title: string): Promise<SavedDoc[] | null> {
  try {
    const id = `v-${Date.now().toString(36)}`;
    await withStore("readwrite", (s) => s.put({ id, title, savedAt: Date.now(), doc, page } satisfies SavedDoc));
    const versions = await listVersions();
    for (const old of versions.slice(MAX_VERSIONS)) await withStore("readwrite", (s) => s.delete(old.id));
    return versions.slice(0, MAX_VERSIONS);
  } catch {
    return null;
  }
}

export async function deleteVersion(id: string): Promise<void> {
  try {
    await withStore("readwrite", (s) => s.delete(id));
  } catch {
    // Sin almacenamiento: nada que borrar.
  }
}
