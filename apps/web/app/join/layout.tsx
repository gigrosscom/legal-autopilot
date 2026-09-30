import type { Metadata } from "next";

// the closed pilot's private link for lawyers: not for search engines
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function JoinLayout({ children }: { children: React.ReactNode }) {
  return children;
}
