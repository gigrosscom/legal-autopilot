import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Arabic } from "next/font/google";
import type { ReactNode } from "react";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

// Inter with cyrillic-ext covers Kazakh letters (ә ғ қ ң ө ұ ү һ і); Arabic gets its own face.
const inter = Inter({ subsets: ["latin", "cyrillic", "cyrillic-ext"], variable: "--font-inter", display: "swap" });
const arabic = Noto_Sans_Arabic({ subsets: ["arabic"], variable: "--font-arabic", display: "swap", preload: false });

export const metadata: Metadata = {
  title: "Konsilier.AI — любая юридическая проблема: от жалобы до решения",
  description: "Готовим документы, подсказываем, куда подать, следим за сроками и подключаем проверенного юриста.",
  // Browser auto-translation rewrites text nodes behind React's back and crashes live pages (chat, forms).
  other: { google: "notranslate" },
};

export const viewport: Viewport = { themeColor: "#f7f4ee", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" dir="ltr" translate="no" className={`notranslate ${inter.variable} ${arabic.variable}`}>
      <body className="flex min-h-screen flex-col antialiased">
        <LangProvider>
          <Header />
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:py-12">{children}</main>
          <Footer />
        </LangProvider>
      </body>
    </html>
  );
}
