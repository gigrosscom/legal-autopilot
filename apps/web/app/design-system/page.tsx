import type { Metadata } from "next";
import { notFound } from "next/navigation";
import DesignSystem from "./DesignSystem";

// Internal reference page: not linked from the site and not served in production
// unless explicitly enabled at build time (NEXT_PUBLIC_SHOW_DESIGN_SYSTEM=1, e.g. locally).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function Page() {
  if (process.env.NEXT_PUBLIC_SHOW_DESIGN_SYSTEM !== "1") notFound();
  return <DesignSystem />;
}
