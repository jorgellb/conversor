// Prueba de carga (16.1): 50 trabajos simultáneos de comprimir-pdf y 10 de ogg-a-mp3, más un pico de
// 300 trabajos ligeros en 5 minutos desde 100 clientes. Se ejecuta contra el Compose de desarrollo:
//   k6 run -e API=http://localhost:8000 -e UPLOAD=http://localhost:8080/files/ -e WEB=http://localhost:3000 tests/load/k6.js
// Las muestras salen de scripts/fixtures/generate.py (FIXTURES=/ruta/a/muestras).
import http from "k6/http";
import { check, sleep } from "k6";
import encoding from "k6/encoding";
import { Trend, Counter } from "k6/metrics";

const API = __ENV.API || "http://localhost:8000";
const UPLOAD = __ENV.UPLOAD || "http://localhost:8080/files/";
const WEB = __ENV.WEB || "http://localhost:3000";
const FIXTURES = __ENV.FIXTURES || "./muestras";
const PDF = open(`${FIXTURES}/fotos.pdf`, "b");
const OGG = open(`${FIXTURES}/voz.ogg`, "b");

const jobTime = new Trend("tiempo_trabajo_ms", true);
const queueFull = new Counter("queue_full");

export const options = {
  scenarios: {
    comprimir: { executor: "per-vu-iterations", vus: 50, iterations: 1, exec: "comprimir", maxDuration: "15m" },
    audio: { executor: "per-vu-iterations", vus: 10, iterations: 1, exec: "audio", maxDuration: "15m" },
    pico: { executor: "ramping-arrival-rate", startRate: 0, timeUnit: "1s", preAllocatedVUs: 100, maxVUs: 100,
            stages: [{ target: 1, duration: "1m" }, { target: 1, duration: "3m" }, { target: 0, duration: "1m" }], exec: "ligero",
            startTime: "30s" },
    paginas: { executor: "constant-vus", vus: 5, duration: "6m", exec: "paginas" },
  },
  thresholds: {
    "http_req_duration{tipo:pagina}": ["p(95)<1000"],
    checks: ["rate>0.95"],
  },
};

function anonToken() {
  const res = http.post(`${API}/v1/session/anon`, JSON.stringify({ turnstile_token: "XXXX.DUMMY.TOKEN.XXXX" }),
    { headers: { "Content-Type": "application/json" } });
  check(res, { "sesión anónima": (r) => r.status === 200 });
  return res.json("token");
}

function tusUpload(token, tool, name, data) {
  const meta = `filename ${encoding.b64encode(name)},tool ${encoding.b64encode(tool)}`;
  const create = http.post(UPLOAD, null, { headers: { Authorization: `Bearer ${token}`, "Tus-Resumable": "1.0.0",
    "Upload-Length": String(data.byteLength), "Upload-Metadata": meta } });
  if (!check(create, { "tus creado": (r) => r.status === 201 })) return null;
  const location = create.headers.Location;
  const patch = http.patch(location.startsWith("http") ? location : `${UPLOAD.replace(/\/files\/$/, "")}${location}`, data, {
    headers: { Authorization: `Bearer ${token}`, "Tus-Resumable": "1.0.0", "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream" } });
  check(patch, { "tus subido": (r) => r.status === 204 });
  return location.split("/").filter(Boolean).pop();
}

function runJob(tool, name, data, options) {
  const token = anonToken();
  const id = tusUpload(token, tool, name, data);
  if (!id) return;
  const started = Date.now();
  const res = http.post(`${API}/v1/jobs`, JSON.stringify({ tool, upload_ids: [id], options }),
    { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
  if (res.status === 503 || (res.status === 429 && res.json("error.code") === "QUEUE_FULL")) {
    queueFull.add(1);
    return;
  }
  check(res, { "trabajo creado": (r) => r.status === 201 });
  let job = res.json();
  while (job && !["succeeded", "failed", "cancelled", "expired"].includes(job.status)) {
    sleep(2);
    job = http.get(`${API}/v1/jobs/${job.id}`, { headers: { Authorization: `Bearer ${token}` } }).json();
  }
  jobTime.add(Date.now() - started, { tool });
  check(job, { "trabajo terminado": (j) => j.status === "succeeded" });
}

export function comprimir() { runJob("comprimir-pdf", "fotos.pdf", PDF, { nivel: "equilibrado" }); }
export function audio() { runJob("ogg-a-mp3", "voz.ogg", OGG, { calidad: "128" }); }
export function ligero() { runJob("comprimir-pdf", "fotos.pdf", PDF, { nivel: "sin_perdida" }); }
export function paginas() {
  const res = http.get(`${WEB}/es/comprimir-pdf`, { tags: { tipo: "pagina" } });
  check(res, { "página 200": (r) => r.status === 200 });
  sleep(1);
}
