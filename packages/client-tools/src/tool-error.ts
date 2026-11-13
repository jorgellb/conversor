// Sin dependencias: lo importan también los módulos ligeros que usa la web en el hilo principal.

/** Error con código estable (docs/ERRORS.md); la web lo traduce con los mensajes de la API. */
export class ToolError extends Error {
  readonly code: string;

  constructor(code: string, detail = "") {
    super(detail || code);
    this.code = code;
    this.name = "ToolError";
  }
}
