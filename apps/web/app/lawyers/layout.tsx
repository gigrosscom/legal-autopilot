import { notFound } from "next/navigation";

import { LAWYERS_PUBLIC } from "@/lib/features";

export default function LawyersLayout({ children }: { children: React.ReactNode }) {
  if (!LAWYERS_PUBLIC) notFound();
  return children;
}
