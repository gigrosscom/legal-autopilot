import type { Metadata } from "next";
import { DemoCase } from "./DemoCase";

// Demo for the talks with lawyers (owner 02.10): a case screen with made-up lawyers, each marked «Пример профиля».
// Reached only by the link from /ops; never indexed, never linked from the site.
export const metadata: Metadata = { title: "Демо: выбор юриста", robots: { index: false, follow: false } };

export default function Page() {
  return <DemoCase />;
}
