import type { Metadata } from "next";

// its own canonical address (the root layout gives the home page's)
export const metadata: Metadata = { alternates: { canonical: "/coverage" } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
