// D-236: el polyfill de `util` que traen mammoth y jszip usa is-generator-function, que prueba `Function("return
// function*() {}")()`: con la CSP sin 'unsafe-eval' eso queda como violación (la captura, pero se anota). Esta versión
// da el mismo resultado sin construir funciones a partir de texto.
"use strict";

const toString = Function.prototype.toString;
const generator = /^\s*(?:async\s+)?function\s*\*/;

module.exports = function isGeneratorFunction(fn) {
  if (typeof fn !== "function") return false;
  if (generator.test(toString.call(fn))) return true;
  return Object.prototype.toString.call(fn) === "[object GeneratorFunction]" || Object.prototype.toString.call(fn) === "[object AsyncGeneratorFunction]";
};
