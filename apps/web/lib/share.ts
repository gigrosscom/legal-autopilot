"use client";

/** Files shared to the installed app from other apps (Web Share Target): public/sw.js keeps them in this cache until
 *  the /share page uploads them to a case. Nothing else is ever stored there. */
const SHARED = "konsilier-shared";

export async function sharedFiles(): Promise<File[]> {
  if (typeof caches === "undefined") return [];
  try {
    const cache = await caches.open(SHARED);
    const keys = [...(await cache.keys())].sort((a, b) => a.url.localeCompare(b.url, undefined, { numeric: true }));
    const files: File[] = [];
    for (const req of keys) {
      const res = await cache.match(req);
      if (!res) continue;
      const blob = await res.blob();
      const name = decodeURIComponent(res.headers.get("X-Filename") ?? "file");
      files.push(new File([blob], name, { type: blob.type || res.headers.get("Content-Type") || "" }));
    }
    return files;
  } catch {
    return [];
  }
}

export async function clearShared(): Promise<void> {
  if (typeof caches === "undefined") return;
  try { await caches.delete(SHARED); } catch {}
}
