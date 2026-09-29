"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LAST_CASE_KEY } from "@/components/AppNav";

/** «Чат» (the app shortcut): the latest conversation, or a new one. */
export default function ChatHome() {
  const router = useRouter();
  useEffect(() => {
    let last: string | null = null;
    try { last = localStorage.getItem(LAST_CASE_KEY); } catch {}
    router.replace(last ? `/chat/${last}` : "/start");
  }, [router]);
  return null;
}
