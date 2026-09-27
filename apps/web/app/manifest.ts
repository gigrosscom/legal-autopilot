import type { MetadataRoute } from "next";

// Installable app (PWA): home screen on iPhone / Android, a window of its own on Mac / Windows.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Konsilier.AI — ИИ-помощник в юридических вопросах",
    short_name: "Konsilier",
    description: "Опишите проблему — подготовим документ, подскажем, куда подать, и проследим за сроками.",
    lang: "ru",
    start_url: "/?source=app",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#f7f4ee",
    theme_color: "#f7f4ee",
    categories: ["legal", "productivity", "utilities"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Новое дело", short_name: "Новое дело", url: "/start?source=app",
        icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }] },
      { name: "Мои дела", short_name: "Мои дела", url: "/cases?source=app",
        icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }] },
    ],
  };
}
