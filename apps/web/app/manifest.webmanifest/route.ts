import type { MetadataRoute } from "next";

const ICON = [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }];

// Installable app (PWA): home screen on iPhone / Android, a window of its own on Mac / Windows. The same manifest
// feeds the store packages (docs/app-stores.md): Trusted Web Activity on Google Play, PWABuilder for Microsoft Store.
// Served at /manifest.webmanifest by this route (not the app/manifest.ts convention, which Next links on every page):
// the root layout links it, and the owner's command centre (/ops) links its own public/ops.webmanifest instead.
export const dynamic = "force-static";

export function GET() {
  return new Response(JSON.stringify(manifest()), { headers: { "Content-Type": "application/manifest+json" } });
}

function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Konsilier",
    short_name: "Консильер",
    description: "ИИ-помощник по правовым вопросам: опишите проблему — подготовим документ, подскажем, куда подать, и проследим за сроками.",
    lang: "ru",
    dir: "ltr",
    start_url: "/?source=app",
    scope: "/",
    display: "standalone",
    orientation: "any",
    // site tokens (app/globals.css): --color-surface for both, so the splash screen and the title bar match the pages
    background_color: "#ffffff",
    theme_color: "#ffffff",
    categories: ["legal", "productivity"],
    prefer_related_applications: false,
    // lets the site ask Chrome whether this app is already installed (navigator.getInstalledRelatedApps)
    related_applications: [{ platform: "webapp", url: "https://konsilier.com/manifest.webmanifest" }],
    launch_handler: { client_mode: ["navigate-existing", "auto"] },
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icons/badge-96.png", sizes: "96x96", type: "image/png", purpose: "monochrome" },
    ],
    shortcuts: [
      { name: "Новое дело", short_name: "Новое дело", url: "/start?source=app", icons: ICON },
      { name: "Мои дела", short_name: "Мои дела", url: "/cases?source=app", icons: ICON },
      { name: "Чат", short_name: "Чат", url: "/chat?source=app", icons: ICON },
    ],
    // Android: «Поделиться» → Консильер in the gallery, files or mail; public/sw.js keeps the files and opens /share.
    share_target: {
      action: "/share-target",
      method: "POST",
      enctype: "multipart/form-data",
      params: {
        files: [{
          name: "files",
          accept: ["image/*", "application/pdf", ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"],
        }],
      },
    },
  };
}
