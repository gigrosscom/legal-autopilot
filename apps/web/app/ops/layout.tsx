import type { Metadata } from "next";
import type { ReactNode } from "react";

// «Konsilier Ops» (PM 01.10, the owner's «да») — the owner's command centre, installable as an app of its own next to the client app:
// its own manifest (public/ops.webmanifest, scope /ops), icon and name on the home screen / in the Dock. The site's
// service worker (public/sw.js, scope "/") serves both apps. This segment's `manifest` replaces the root one on /ops.
export const metadata: Metadata = {
  title: "Konsilier Ops",
  description: "Командный центр владельца Konsilier AI: цели и курс, команда, задачи, решения, отчёты и операции.",
  manifest: "/ops.webmanifest",
  applicationName: "Konsilier Ops",
  appleWebApp: { capable: true, title: "Ops", statusBarStyle: "default" },
  icons: {
    icon: [{ url: "/icons/ops/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/ops/apple-touch-icon.png", sizes: "180x180" }],
  },
  robots: { index: false, follow: false },
};

export default function OpsLayout({ children }: { children: ReactNode }) {
  return children;
}
