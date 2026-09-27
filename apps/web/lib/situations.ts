import type { IconName } from "@/components/ui";

/** Life situations shown instead of branches of law. Each opens the same intake with a hint. */
export const SITUATIONS: { key: string; icon: IconName; branch: string; religious?: boolean }[] = [
  { key: "cheated", icon: "cart", branch: "consumer" },
  { key: "fired", icon: "briefcase", branch: "labor" },
  { key: "family", icon: "family", branch: "family" },
  { key: "fine", icon: "receipt", branch: "administrative" },
  { key: "crime", icon: "shield", branch: "criminal" },
  { key: "stateBody", icon: "landmark", branch: "administrative" },
  { key: "bank", icon: "coin", branch: "finance" },
  { key: "business", icon: "handshake", branch: "commercial" },
  { key: "inheritance", icon: "scroll", branch: "inheritance" },
  { key: "housing", icon: "home", branch: "housing" },
  { key: "religious", icon: "community", branch: "family", religious: true },
];
