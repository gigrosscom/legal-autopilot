// Konsilier.AI service worker — makes the site installable, survives a lost connection, shows push notifications
// and receives files shared to the app from other apps (Android: «Поделиться» → Консильер).
// Privacy: cases and personal data are never cached. Only the app shell is: hashed build assets
// (/_next/static, immutable), icons and the offline page. API calls go to another origin and are not touched.
// Files shared to the app wait in the SHARED cache only until the /share page uploads them to a case or drops them.
const VERSION = "konsilier-v2";
const SHARED = "konsilier-shared";
const OFFLINE = "/offline";
const PRECACHE = [OFFLINE, "/icons/icon-192.png", "/icons/icon-512.png", "/icons/badge-96.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== SHARED).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Web Share Target (manifest share_target): keep the files, then open /share to choose the case.
async function receiveShare(request) {
  const form = await request.formData();
  const files = form.getAll("files").filter((f) => f && typeof f === "object" && f.size > 0);
  await caches.delete(SHARED);
  const cache = await caches.open(SHARED);
  await Promise.all(files.map((f, i) => cache.put(`/shared/${i}`, new Response(f, {
    headers: { "Content-Type": f.type || "application/octet-stream", "X-Filename": encodeURIComponent(f.name || `file-${i + 1}`) },
  }))));
  return Response.redirect(`/share?n=${files.length}`, 303);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.method === "POST" && url.pathname === "/share-target") {
    event.respondWith(receiveShare(req).catch(() => Response.redirect("/share?error=1", 303)));
    return;
  }
  if (req.method !== "GET") return;

  // Pages: always from the network (fresh after every deploy); the offline page when there is no network.
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
    return;
  }
  // Hashed build assets and icons never change: cache first.
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      })),
    );
  }
});

// Push from the API (konsilier/core/push.py): {title, body, url}.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : "" }; }
  event.waitUntil(self.registration.showNotification(data.title || "Konsilier", {
    body: data.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    data: { url: data.url || "/cases" },
  }));
});

// A tap on the notification: bring the open app / tab to the page, or open it.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/cases", self.location.origin);
  if (target.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const client = open.find((c) => new URL(c.url).origin === self.location.origin);
    if (client) {
      try {
        await client.focus();
        await client.navigate(target.href);
        return;
      } catch { /* not controlled by this worker yet: open a window instead */ }
    }
    await self.clients.openWindow(target.href);
  })());
});
