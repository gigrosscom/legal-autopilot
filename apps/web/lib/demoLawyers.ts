// «Пример профиля» — demo lawyers for the talks with lawyers (owner 02.10). Everything here is made up: no real
// person, no photo, names cut to a first name and an initial. Shown ONLY on /case/demo (the link from /ops); real
// clients see the pilot's real lawyers or «Скоро: подключаем юристов» — never these (otherwise it is untrue
// advertising). Prices are ordinary for Almaty and Astana in 2026.

export type ChoiceLawyer = {
  id: string;
  name: string;
  kind: string;          // «Адвокат», «Юридический консультант»
  organization?: string;
  city: string;
  specializations: string[];
  price: number;
  priceNote?: string;
  response: string;      // «в течение 2 часов»
  rating?: { score: number; cases: number; success: number; reviews: number } | null;
  demo?: boolean;
};

export const DEMO_LAWYERS: ChoiceLawyer[] = [
  { id: "demo-a", name: "Айгерим Н.", kind: "Адвокат", organization: "Коллегия адвокатов", city: "Алматы",
    specializations: ["Защита прав потребителей", "Банки и МФО"], price: 25000, priceNote: "претензия и сопровождение до ответа",
    response: "в течение 2 часов", rating: { score: 4.8, cases: 96, success: 0.81, reviews: 118 }, demo: true },
  { id: "demo-b", name: "Ерлан К.", kind: "Юридический консультант", organization: "Палата юридических консультантов", city: "Астана",
    specializations: ["Трудовые споры", "Зарплата и увольнение"], price: 18000, priceNote: "разбор и заявление в согласительную комиссию",
    response: "в течение 4 часов", rating: { score: 4.6, cases: 64, success: 0.72, reviews: 73 }, demo: true },
  { id: "demo-c", name: "Динара С.", kind: "Адвокат", organization: "Коллегия адвокатов", city: "Алматы",
    specializations: ["Жильё и аренда", "Семейные споры"], price: 30000, priceNote: "иск и представительство — по договорённости",
    response: "в течение рабочего дня", rating: { score: 4.7, cases: 51, success: 0.76, reviews: 44 }, demo: true },
  { id: "demo-d", name: "Тимур Ж.", kind: "Юридический консультант", city: "Астана",
    specializations: ["Штрафы и госорганы", "Административные жалобы"], price: 12000, priceNote: "жалоба на постановление",
    response: "в течение 3 часов", rating: { score: 4.5, cases: 39, success: 0.69, reviews: 31 }, demo: true },
  { id: "demo-e", name: "Мадина А.", kind: "Адвокат", organization: "Коллегия адвокатов", city: "Астана",
    specializations: ["Банки и МФО", "Мошенничество с кредитами"], price: 35000, priceNote: "обращение в банк и АРРФР",
    response: "в течение рабочего дня", rating: { score: 4.9, cases: 72, success: 0.83, reviews: 90 }, demo: true },
  { id: "demo-f", name: "Арман Б.", kind: "Юридический консультант", city: "Алматы",
    specializations: ["Защита прав потребителей", "Онлайн-сервисы и подписки"], price: 15000, priceNote: "претензия исполнителю",
    response: "в течение 2 часов", rating: null, demo: true },
];

export function initials(name: string): string {
  return name.replace(/[«»"()]/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
}
