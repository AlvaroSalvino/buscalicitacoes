/* Service worker do PWA Busca Licitações.
 * - Shell (HTML/CSS/JS/ícones): cache-first com atualização em segundo plano.
 * - GET /api/licitacoes*: network-first, cai no cache se estiver offline.
 * - Demais chamadas de API (auth, alertas, notificações): nunca cacheadas.
 */
const VERSAO = "v2";
const CACHE_SHELL = `shell-${VERSAO}`;
const CACHE_API = `api-${VERSAO}`;
const SHELL = [
  "/",
  "/static/app/app.css",
  "/static/app/app.js",
  "/manifest.webmanifest",
  "/static/app/icon-192.png",
  "/static/app/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_SHELL).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => ![CACHE_SHELL, CACHE_API].includes(k)).map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    if (url.pathname.startsWith("/api/licitacoes") && !req.headers.get("Authorization")) {
      event.respondWith(networkFirst(req));
    }
    return; // o resto vai direto para a rede
  }

  if (url.pathname.startsWith("/admin/")) return;

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/", { ignoreSearch: true }))
    );
    return;
  }

  if (url.pathname.startsWith("/static/") || SHELL.includes(url.pathname)) {
    event.respondWith(staleWhileRevalidate(req));
  }
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE_API);
  try {
    const resp = await fetch(req);
    if (resp.ok) cache.put(req, resp.clone());
    return resp;
  } catch (e) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw e;
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE_SHELL);
  const cached = await cache.match(req);
  const rede = fetch(req)
    .then((resp) => {
      if (resp.ok) cache.put(req, resp.clone());
      return resp;
    })
    .catch(() => cached);
  return cached || rede;
}

/* ---------- Web Push ---------- */
self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) { d = { body: event.data && event.data.text() }; }
  event.waitUntil(
    self.registration.showNotification(d.title || "Busca Licitações", {
      body: d.body || "Há novidades para você.",
      icon: "/static/app/icon-192.png",
      badge: "/static/app/icon-192.png",
      tag: d.tag || "novidades",
      renotify: true,
      data: { url: d.url || "/#/notificacoes" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const alvo = new URL((event.notification.data && event.notification.data.url) || "/#/notificacoes", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (new URL(w.url).origin === self.location.origin && "focus" in w) {
          return w.focus().then(() => ("navigate" in w ? w.navigate(alvo) : null));
        }
      }
      return self.clients.openWindow(alvo);
    })
  );
});
