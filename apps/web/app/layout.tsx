import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Arabic } from "next/font/google";
import type { ReactNode } from "react";
import { PwaRegister } from "@/components/InstallApp";
import { SiteChrome } from "@/components/SiteChrome";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

// Inter with cyrillic-ext covers Kazakh letters (ә ғ қ ң ө ұ ү һ і); Arabic gets its own face.
// "optional": on slow networks the metric-matched fallback stays — no late re-layout of the hero text.
const inter = Inter({ subsets: ["latin", "cyrillic", "cyrillic-ext"], variable: "--font-inter", display: "optional" });
const arabic = Noto_Sans_Arabic({ subsets: ["arabic"], variable: "--font-arabic", display: "swap", preload: false });

export const metadata: Metadata = {
  title: "Konsiliér AI — ИИ-помощник по правовым вопросам",
  description: "Опишите проблему — Konsiliér AI подготовит документ по законам вашей страны, подскажет, куда подать, проследит за сроками, а когда нужно — поможет найти юриста.",
  // Browser auto-translation rewrites text nodes behind React's back and crashes live pages (chat, forms).
  other: { google: "notranslate" },
  // installed app on iPhone / iPad: own icon, full screen, a status bar that matches the site
  appleWebApp: { capable: true, title: "Konsiliér AI", statusBarStyle: "default" },
  icons: { apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }] },
  applicationName: "Konsiliér AI",
  manifest: "/manifest.webmanifest", // app/manifest.webmanifest/route.ts; /ops links its own (app/ops/layout.tsx)
  formatDetection: { telephone: false },
};

// viewportFit "cover": the installed app uses the whole screen; notches are handled with safe-area insets.
// interactiveWidget: the on-screen keyboard shrinks the layout, so input bars stay above it (Android Chrome).
export const viewport: Viewport = {
  themeColor: "#ffffff", width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content",
};

// Chrome / Edge / Samsung Internet fire `beforeinstallprompt` once per page load — often before React and the app's
// code have loaded, so a listener in a component misses it and «Установить» has no dialog to open. This inline script
// runs with the HTML: it keeps the event for the button (components/InstallApp.tsx) and stops the browser's mini-bar.
const INSTALL_CAPTURE =
  "addEventListener('beforeinstallprompt',function(e){e.preventDefault();window.__konsilierInstall=e});"
  + "addEventListener('appinstalled',function(){window.__konsilierInstall=null});";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" dir="ltr" translate="no" className={`notranslate ${inter.variable} ${arabic.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: INSTALL_CAPTURE }} />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <LangProvider>
          <SiteChrome>{children}</SiteChrome>
          <PwaRegister />
        </LangProvider>
      </body>
    </html>
  );
}
