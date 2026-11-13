// Detección por bytes en el navegador (convertir-archivo, 7.22): los mismos casos que core/filetype.py.
import { readFileSync } from "node:fs";
import path from "node:path";

import { zipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { detectHead, detectType, extOfName, normalizeExt, zipEntries, type Reader } from "../src/filetype";

const CASES = JSON.parse(readFileSync(path.join(import.meta.dirname, "../../../tests/fixtures/filetype-cases.json"), "utf-8")).cases as {
  id: string; declared: string; expected: string | null; b64: string;
}[];

function reader(bytes: Uint8Array, log?: [number, number][]): Reader {
  return async (start, end) => {
    log?.push([start, end]);
    return bytes.slice(start, end);
  };
}

describe("detección por bytes, igual que el servidor (casos compartidos)", () => {
  it.each(CASES.map((c) => [c.id, c] as const))("%s", async (_, c) => {
    const bytes = Uint8Array.from(Buffer.from(c.b64, "base64"));
    const found = await detectType(reader(bytes), bytes.length, c.declared);
    expect(found?.ext ?? null).toBe(c.expected);
  });
});

describe("lectura por tramos", () => {
  it("de un ZIP grande solo lee la cabecera, el final y el directorio central", async () => {
    // 20 MB de una entrada guardada sin comprimir y un documento de Word.
    const big = zipSync({ "[Content_Types].xml": new TextEncoder().encode("<Types/>"), "word/document.xml": new Uint8Array(1),
      "word/media/video.bin": [new Uint8Array(20 * 1024 * 1024), { level: 0 }] });
    const log: [number, number][] = [];
    const found = await detectType(reader(big, log), big.length, "docx");
    expect(found).toEqual({ ext: "docx", family: "zip" });
    const read = log.reduce((t, [a, b]) => t + (b - a), 0);
    expect(read).toBeLessThan(200 * 1024);
  });

  it("entradas y «mimetype» de un ODF; un ZIP roto se queda en «zip»", async () => {
    const odt = zipSync({ mimetype: [new TextEncoder().encode("application/vnd.oasis.opendocument.text"), { level: 0 }], "content.xml": new Uint8Array(4) });
    const entries = await zipEntries(reader(odt), odt.length);
    expect(entries).toEqual({ names: ["mimetype", "content.xml"], mimetype: "application/vnd.oasis.opendocument.text" });
    const broken = Uint8Array.from([0x50, 0x4b, 0x03, 0x04, ...new Uint8Array(60)]);
    expect(await detectType(reader(broken), broken.length, "docx")).toEqual({ ext: "zip", family: "zip" });
  });

  it("extensiones y cabecera sin mirar dentro del ZIP", () => {
    expect(normalizeExt(".JPEG")).toBe("jpg");
    expect(extOfName("foto.final.TIF")).toBe("tiff");
    expect(extOfName("sin-extension")).toBe("");
    expect(detectHead(Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 0, 0]))).toEqual({ ext: "zip", family: "zip" });
    expect(detectHead(new Uint8Array(), "txt")).toBeNull();
  });
});
