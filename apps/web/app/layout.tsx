import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Arabic } from "next/font/google";
import type { ReactNode } from "react";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import { PwaRegister } from "@/components/InstallApp";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

// Inter with cyrillic-ext covers Kazakh letters (ә ғ қ ң ө ұ ү һ і); Arabic gets its own face.
// "optional": on slow networks the metric-matched fallback stays — no late re-layout of the hero text.
const inter = Inter({ subsets: ["latin", "cyrillic", "cyrillic-ext"], variable: "--font-inter", display: "optional" });
const arabic = Noto_Sans_Arabic({ subsets: ["arabic"], variable: "--font-arabic", display: "swap", preload: false });

export const metadata: Metadata = {
  title: "Konsilier.AI — ИИ-помощник в юридических вопросах",
  description: "Опишите проблему — Konsilier подготовит документ по законам вашей страны, подскажет, куда подать, проследит за сроками, а когда нужно — подключит проверенного юриста.",
  // Browser auto-translation rewrites text nodes behind React's back and crashes live pages (chat, forms).
  other: { google: "notranslate" },
  // installed app on iPhone / iPad: own icon, full screen, a status bar that matches the site
  appleWebApp: { capable: true, title: "Konsilier", statusBarStyle: "default" },
  icons: { apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }] },
  applicationName: "Konsilier",
  formatDetection: { telephone: false },
};

// viewportFit "cover": the installed app uses the whole screen; notches are handled with safe-area insets.
export const viewport: Viewport = { themeColor: "#f7f4ee", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" dir="ltr" translate="no" className={`notranslate ${inter.variable} ${arabic.variable}`}>
      <body className="flex min-h-screen flex-col antialiased">
        <LangProvider>
          <Header />
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:py-12">{children}</main>
          <Footer />
          <PwaRegister />
        </LangProvider>
      </body>
    </html>
  );
}
