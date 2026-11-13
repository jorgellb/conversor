/** Papel de cada archivo en solicitud-de-empleo-pdf, igual que en el servidor: carta (opcional), CV y adjuntos. */
export function applicationRole(index: number, count: number, firstIsLetter: boolean): "letterRole" | "cvRole" | "attachmentRole" {
  if (firstIsLetter && count > 1) return index === 0 ? "letterRole" : index === 1 ? "cvRole" : "attachmentRole";
  return index === 0 ? "cvRole" : "attachmentRole";
}
