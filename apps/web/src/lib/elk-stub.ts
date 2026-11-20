// D-231: Mermaid carga elkjs (EPL-2.0) solo para la disposición «elk», que esta web no usa (renderMermaid fija dagre).
// next.config.ts apunta elkjs a este módulo para que no se empaquete ni se distribuya.
export default class ELK {
  constructor() {
    throw new Error("La disposición ELK no está disponible");
  }
}
