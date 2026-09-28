import { TELEGRAM_BOT } from "@/lib/api";

// Company contacts shown in the footer. Empty values are not shown — fill them in here.
// Handle rules: Instagram / TikTok / LinkedIn accept "konsilier.ai"; Telegram usernames allow only
// letters, digits and "_" (no dot), so the Telegram link goes to the product bot; WhatsApp needs a phone number.
export const CONTACTS = {
  address: "", // e.g. "Алматы, пр. Абая 1, офис 10"
  email: "info@konsilier.com",
  whatsapp: "", // digits with country code, e.g. "77001234567" → https://wa.me/77001234567
  instagram: "https://www.instagram.com/konsilier.ai",
  tiktok: "https://www.tiktok.com/@konsilier.ai",
  linkedin: "https://www.linkedin.com/company/konsilier.ai",
  telegram: `https://t.me/${TELEGRAM_BOT || "KonsilierAI_bot"}`,
};

export const SOCIALS: { key: "instagram" | "tiktok" | "linkedin" | "telegram" | "whatsapp"; label: string; url: string }[] = [
  { key: "instagram", label: "Instagram", url: CONTACTS.instagram },
  { key: "tiktok", label: "TikTok", url: CONTACTS.tiktok },
  { key: "linkedin", label: "LinkedIn", url: CONTACTS.linkedin },
  { key: "telegram", label: "Telegram", url: CONTACTS.telegram },
  { key: "whatsapp", label: "WhatsApp", url: CONTACTS.whatsapp ? `https://wa.me/${CONTACTS.whatsapp}` : "" },
].filter((s) => s.url) as { key: "instagram" | "tiktok" | "linkedin" | "telegram" | "whatsapp"; label: string; url: string }[];
