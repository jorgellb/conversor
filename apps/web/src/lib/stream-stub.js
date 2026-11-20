// D-236: en el navegador nadie usa los flujos de Node. jszip (de mammoth y docx) solo los pide para su salida de Node y
// comprueba si existen; el polyfill (stream-browserify → readable-stream → util) traía un `Function(...)` que la CSP
// anota. Sin flujos, jszip usa sus salidas del navegador (Blob y Uint8Array).
"use strict";

module.exports = {};
