"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AppTopBar, isAppRoute, Sidebar, TabBar } from "@/components/AppNav";
import Footer from "@/components/Footer";
import Header from "@/components/Header";

/** The website gets the header and footer; the app (chat, cases, documents, profile) gets its own navigation. */
export function SiteChrome({ children }: { children: ReactNode }) {
  const path = usePathname();
  if (isAppRoute(path)) {
    return (
      <>
        <Sidebar />
        <div className="flex min-h-screen flex-1 flex-col lg:ps-64">
          <AppTopBar />
          <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-5 pt-6 pb-28 md:pt-10 lg:px-10 lg:pb-12">{children}</main>
        </div>
        <TabBar />
      </>
    );
  }
  return (
    <>
      <Header />
      <main id="main" className="mx-auto w-full max-w-[1208px] flex-1 px-5 py-8 md:py-12">{children}</main>
      <Footer />
    </>
  );
}
