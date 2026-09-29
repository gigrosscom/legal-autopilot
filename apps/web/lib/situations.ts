import type { IconName } from "@/components/ui";

/** Life situations shown instead of branches of law. Each opens the same intake with a hint. ``topics`` are the
 *  taxonomy prefixes whose scenarios and disputes give the chat its suggestions (GET /v1/examples), so a new
 *  scenario adds its own examples without touching the site. */
export const SITUATIONS: { key: string; icon: IconName; branch: string; topics: string[] }[] = [
  { key: "cheated", icon: "cart", branch: "consumer", topics: ["consumer"] },
  { key: "fired", icon: "briefcase", branch: "labor", topics: ["labor"] },
  { key: "family", icon: "family", branch: "family", topics: ["family"] },
  { key: "fine", icon: "receipt", branch: "administrative", topics: ["administrative.fine_appeal"] },
  { key: "crime", icon: "shield", branch: "criminal", topics: ["criminal.crime_report", "criminal.police_inaction"] },
  { key: "stateBody", icon: "landmark", branch: "administrative", topics: ["administrative.state_body_inaction"] },
  { key: "bank", icon: "coin", branch: "finance", topics: ["finance"] },
  { key: "business", icon: "handshake", branch: "commercial", topics: ["commercial", "tax"] },
  { key: "inheritance", icon: "scroll", branch: "inheritance", topics: ["inheritance"] },
  { key: "housing", icon: "home", branch: "housing", topics: ["housing", "civil.damages"] },
  { key: "benefits", icon: "users", branch: "social", topics: ["social"] },
  { key: "grants", icon: "chart", branch: "business", topics: ["business"] },
  { key: "study", icon: "graduation", branch: "education", topics: ["education"] },
  { key: "tenders", icon: "building", branch: "procurement", topics: ["procurement"] },
];
