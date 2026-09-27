import type { Metadata } from "next";
import type { ReactNode } from "react";
import Header from "@/components/Header";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "Konsilier.AI — ваше дело от первого документа до результата",
  description: "Готовые претензии и жалобы по законам Казахстана, подача, контроль сроков и проверенные юристы, которые доведут дело до результата.",
  // Browser auto-translation rewrites text nodes behind React's back and crashes live pages (chat, forms).
  other: { google: "notranslate" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" translate="no" className="notranslate">
      <body className="min-h-screen antialiased">
        <LangProvider>
          <Header />
          <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
          <footer className="mx-auto max-w-5xl px-4 pb-10 text-xs text-ink/50">
            © Konsilier.AI · konsilier.com · konsilier.ai
          </footer>
        </LangProvider>
      </body>
    </html>
  );
}
