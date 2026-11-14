// Prueba de carga de 16.1: 50 trabajos simultáneos de comprimir-pdf y 10 de ogg-a-mp3, más un pico de 300 trabajos
// ligeros en 5 minutos desde 100 clientes, midiendo el tiempo de respuesta de las páginas (por debajo de 1 s) y la espera
// en cola (QUEUE_FULL tiene que llegar antes de que la espera supere el umbral de 4.5). Los números están en
// escenarios.json, que comprueba tests/test_carga_k6.py. CPU, RAM y disco los mide tests/load/recursos.sh a la vez.
//
// La ejecuta el propietario en el VPS (o en una máquina con el Compose completo); pasos en docs/OPERATIONS.md:
//   python scripts/fixtures/generate.py /tmp/muestras    (las muestras: fotos.pdf, texto.pdf y voz.ogg)
//   sh tests/load/recursos.sh recursos-k6.csv &          (en el servidor, mientras dura la prueba)
//   k6 run -e API=https://api.ejemplo.com -e UPLOAD=https://upload.ejemplo.com/files/ -e WEB=https://ejemplo.com \
//          -e FIXTURES=/tmp/muestras -e SALIDA=resultados-k6.json tests/load/k6.js
// Todos los clientes virtuales salen de la misma IP: durante la prueba hacen falta las claves de prueba de Turnstile
// (0.1) y límites por IP altos (RATE_LIMIT_PER_MINUTE y ANON_TOKENS_PER_IP_DAY, ver OPERATIONS.md). Si no, la prueba
// mide el limitador y no las colas: por eso falla en cuanto aparece un RATE_LIMITED.
import http from "k6/http";
import { check, sleep } from "k6";
import encoding from "k6/encoding";
import { Counter, Trend } from "k6/metrics";

const E = JSON.parse(open("./escenarios.json"));

const API = (__ENV.API || "http://localhost:8000").replace(/\/$/, "");
const UPLOAD = __ENV.UPLOAD || "http://localhost:8080/files/";
const WEB = (__ENV.WEB || "http://localhost:3000").replace(/\/$/, "");
const FIXTURES = __ENV.FIXTURES || "./muestras";
const TURNSTILE = __ENV.TURNSTILE_TOKEN || "XXXX.DUMMY.TOKEN.XXXX";

// `open` solo funciona al cargar el script: se leen aquí las tres muestras.
const SAMPLES = {};
for (const key of ["comprimir", "audio", "pico"]) SAMPLES[E[key].muestra] = open(`${FIXTURES}/${E[key].muestra}`, "b");

// Grupo de worker de cada herramienta (registro): la espera máxima de 4.5 es por grupo.
const GROUP = { "comprimir-pdf": "pdf", "ogg-a-mp3": "av" };

const jobTime = new Trend("tiempo_trabajo_ms", true);
const queueWait = new Trend("espera_cola_ms", true);
const queueFull = new Counter("queue_full");
const rateLimited = new Counter("rate_limited");
const failedJobs = new Counter("trabajos_fallidos");

const thresholds = {
  "http_req_duration{tipo:pagina}": [`p(99)<${E.umbrales.pagina_ms}`],
  rate_limited: ["count==0"],
  trabajos_fallidos: ["count==0"],
  // El pico tiene que llegar entero: si no quedan clientes libres, k6 descarta llegadas y la prueba no vale.
  dropped_iterations: ["count==0"],
  checks: ["rate>0.95"],
};
for (const [tool, group] of Object.entries(GROUP)) {
  thresholds[`espera_cola_ms{herramienta:${tool}}`] = [`max<${E.umbrales.espera_cola_s[group] * 1000}`];
}

export const options = {
  scenarios: {
    comprimir: { executor: "per-vu-iterations", vus: E.comprimir.trabajos_simultaneos, iterations: 1, exec: "comprimir", maxDuration: E.duracion_maxima },
    audio: { executor: "per-vu-iterations", vus: E.audio.trabajos_simultaneos, iterations: 1, exec: "audio", maxDuration: E.duracion_maxima },
    // 300 llegadas repartidas en 5 minutos (una por segundo), atendidas por 100 clientes con su propia sesión.
    pico: {
      executor: "constant-arrival-rate", rate: E.pico.trabajos, timeUnit: `${E.pico.minutos}m`, duration: `${E.pico.minutos}m`,
      preAllocatedVUs: E.pico.clientes, maxVUs: E.pico.clientes, exec: "ligero", startTime: E.pico.empieza,
    },
    paginas: { executor: "constant-vus", vus: E.paginas.clientes, duration: `${E.paginas.minutos}m`, exec: "paginas" },
  },
  thresholds,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
};

// Cada usuario virtual es un cliente: una sesión anónima por VU (las variables del módulo son de cada VU).
let token = null;

function anonToken() {
  if (token) return token;
  const res = http.post(`${API}/v1/session/anon`, JSON.stringify({ turnstile_token: TURNSTILE }),
    { headers: { "Content-Type": "application/json" }, tags: { tipo: "api" } });
  if (res.status === 429) rateLimited.add(1);
  if (!check(res, { "sesión anónima": (r) => r.status === 200 })) return null;
  token = res.json("token");
  return token;
}

function auth(extra) {
  return Object.assign({ Authorization: `Bearer ${token}` }, extra || {});
}

function tusUpload(tool, name, data) {
  const meta = `filename ${encoding.b64encode(name)},tool ${encoding.b64encode(tool)}`;
  const create = http.post(UPLOAD, null, {
    headers: auth({ "Tus-Resumable": "1.0.0", "Upload-Length": String(data.byteLength), "Upload-Metadata": meta }), tags: { tipo: "subida" },
  });
  if (!check(create, { "tus creado": (r) => r.status === 201 })) return null;
  const location = create.headers.Location;
  const target = location.startsWith("http") ? location : `${UPLOAD.match(/^https?:\/\/[^/]+/)[0]}${location}`;
  const patch = http.patch(target, data, {
    headers: auth({ "Tus-Resumable": "1.0.0", "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream" }), tags: { tipo: "subida" },
  });
  if (!check(patch, { "tus subido": (r) => r.status === 204 })) return null;
  return location.split("/").filter(Boolean).pop();
}

function errorCode(res) {
  try {
    return res.json("error.code");
  } catch (e) {
    return null;
  }
}

function runJob(scenario) {
  const { herramienta: tool, muestra: name, opciones } = E[scenario];
  if (!anonToken()) return;
  const id = tusUpload(tool, name, SAMPLES[name]);
  if (!id) return;
  const started = Date.now();
  const res = http.post(`${API}/v1/jobs`, JSON.stringify({ tool, upload_ids: [id], options: opciones }),
    { headers: auth({ "Content-Type": "application/json" }), tags: { tipo: "api" } });
  const code = errorCode(res);
  if (res.status === 503 && code === "QUEUE_FULL") {
    // Lo esperado cuando la cola pasa del umbral (4.5): se rechaza enseguida en vez de dejar esperando.
    queueFull.add(1, { herramienta: tool });
    return;
  }
  if (res.status === 429) rateLimited.add(1);
  if (!check(res, { "trabajo creado": (r) => r.status === 201 })) return;
  let job = res.json();
  let waited = null;
  while (job && !["succeeded", "failed", "cancelled", "expired"].includes(job.status)) {
    sleep(E.sondeo_s);
    const poll = http.get(`${API}/v1/jobs/${job.id}`, { headers: auth(), tags: { tipo: "api", name: "GET /v1/jobs/:id" } });
    if (poll.status === 429) rateLimited.add(1);
    if (poll.status !== 200) continue;
    job = poll.json();
    if (waited === null && job.status !== "queued") waited = Date.now() - started;
  }
  queueWait.add(waited === null ? Date.now() - started : waited, { herramienta: tool });
  jobTime.add(Date.now() - started, { herramienta: tool });
  if (!check(job, { "trabajo terminado": (j) => j.status === "succeeded" })) failedJobs.add(1, { herramienta: tool });
}

export function comprimir() { runJob("comprimir"); }
export function audio() { runJob("audio"); }
export function ligero() { runJob("pico"); }

export function paginas() {
  for (const ruta of E.paginas.rutas) {
    const res = http.get(`${WEB}${ruta}`, { tags: { tipo: "pagina", name: ruta } });
    check(res, { "página 200": (r) => r.status === 200 });
    sleep(1);
  }
}

function stat(data, metric, value) {
  const m = data.metrics[metric];
  return m && m.values && m.values[value] !== undefined ? m.values[value] : "—";
}

/** Resumen para copiar a docs/OPERATIONS.md, y todas las métricas en JSON (SALIDA). */
export function handleSummary(data) {
  const lines = [
    "Prueba de carga 16.1",
    `páginas: p95 ${stat(data, "http_req_duration{tipo:pagina}", "p(95)")} ms, p99 ${stat(data, "http_req_duration{tipo:pagina}", "p(99)")} ms, máx. ${stat(data, "http_req_duration{tipo:pagina}", "max")} ms`,
    `espera en cola comprimir-pdf: máx. ${stat(data, "espera_cola_ms{herramienta:comprimir-pdf}", "max")} ms (umbral ${E.umbrales.espera_cola_s.pdf * 1000})`,
    `espera en cola ogg-a-mp3: máx. ${stat(data, "espera_cola_ms{herramienta:ogg-a-mp3}", "max")} ms (umbral ${E.umbrales.espera_cola_s.av * 1000})`,
    `tiempo de trabajo: p50 ${stat(data, "tiempo_trabajo_ms", "med")} ms, p95 ${stat(data, "tiempo_trabajo_ms", "p(95)")} ms`,
    `QUEUE_FULL: ${stat(data, "queue_full", "count")}; RATE_LIMITED: ${stat(data, "rate_limited", "count")}; fallidos: ${stat(data, "trabajos_fallidos", "count")}; descartados: ${stat(data, "dropped_iterations", "count")}`,
  ];
  return { stdout: `${lines.join("\n")}\n`, [__ENV.SALIDA || "resultados-k6.json"]: JSON.stringify(data, null, 2) };
}
