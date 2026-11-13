// Service worker (8.3): las herramientas de navegador siguen funcionando sin conexión una vez visitadas.
const CACHE = "conversor-v3";
// El WebAssembly (/codecs/, con el resumen del contenido en el nombre) se guarda la primera vez que se usa.
const PRECACHE = ["/fonts/NotoSans-Regular.ttf", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  const immutable = url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/codecs/") || url.pathname.startsWith("/fonts/") ||
    url.pathname.startsWith("/opencv/");
  if (immutable) {
    // Recursos versionados: primero la caché.
    event.respondWith(
      caches.match(event.request).then((hit) => hit || fetch(event.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return res;
      })),
    );
    return;
  }
  if (event.request.mode === "navigate") {
    // Páginas: primero la red; sin conexión, la última copia.
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
          return res;
        })
        .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/es"))),
    );
  }
});
