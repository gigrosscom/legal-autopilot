"use client";

import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { AppTopBar, isAppRoute, Sidebar, TabBar } from "@/components/AppNav";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import { AppBanner } from "@/components/InstallApp";
import { captureReferral } from "@/lib/api";

/** The website gets the header and footer; the app (chat, cases, documents, profile) gets its own navigation. */
export function SiteChrome({ children }: { children: ReactNode }) {
  const path = usePathname();
  useEffect(() => { captureReferral(); }, []);
  useEffect(() => {  // the chat's look (messenger | whatsapp): ?look=… to preview, remembered on this device
    try {
      const q = new URLSearchParams(window.location.search).get("look");
      if (q === "messenger" || q === "whatsapp") localStorage.setItem("konsilier.look", q);
      document.documentElement.dataset.look = localStorage.getItem("konsilier.look") ?? "messenger";
    } catch { document.documentElement.dataset.look = "messenger"; }
  }, []);
  if (isAppRoute(path)) {
    return (
      <>
        <Sidebar />
        <div className="flex min-h-screen flex-1 flex-col lg:ps-64">
          <AppTopBar />
          <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-5 pt-6 pb-28 md:pt-10 lg:px-10 lg:pb-12">{children}</main>
        </div>
        <TabBar />
        <AppBanner above />
      </>
    );
  }
  return (
    <>
      <Header />
      <main id="main" className="mx-auto w-full max-w-[1208px] flex-1 px-5 py-8 md:py-12">{children}</main>
      <Footer />
      <AppBanner />
    </>
  );
}
