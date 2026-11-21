// Pegamento de Emscripten de draco3d (Apache-2.0): una fábrica que recibe las opciones del módulo (D-257).
declare module "draco3d/draco_encoder_nodejs.js" {
  const factory: (opts: object) => Promise<unknown>;
  export default factory;
}
declare module "draco3d/draco_decoder_nodejs.js" {
  const factory: (opts: object) => Promise<unknown>;
  export default factory;
}
