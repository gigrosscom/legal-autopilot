import type { Metadata } from "next";
import type { ReactNode } from "react";
import Header from "@/components/Header";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "Konsilier.AI — юридическая проблема до результата",
  description: "Готовые документы, подача, контроль сроков и эскалация до результата.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
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
