"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "ru" | "kk";

type Dict = { [key: string]: string | Dict };

const ru: Dict = {
  nav: { start: "Начать", cases: "Мои дела", admin: "Админка", lawyers: "Юристы", forLawyers: "Для юристов" },
  roadmap: {
    title: "Дорожная карта дела",
    best: "Лучший вариант",
    worst: "Если потребуются все шаги",
    openEnded: "затем — работа с юристом, сроки по договорённости",
    done: "Готово",
    current: "Сейчас",
    upcoming: "Дальше",
    skipped: "Не понадобилось",
    ifNeeded: "если потребуется",
    due: "срок",
    estimated: "ориентировочно",
    finished: "завершено",
    todoNorm: "срок уточняется юристом",
  },
  trust: {
    title: "Как мы защищаем от мошенничества и пустых обещаний",
    verifiedTitle: "Только проверенные юристы",
    verified: "Статус адвоката или юрконсультанта сверяется с реестрами, личность — через ЭЦП. Нет проверки — нет доступа к клиентам.",
    escrowTitle: "Оплата по этапам, деньги в резерве",
    escrow: "Вы не платите всё вперёд. Сумма резервируется у платёжного партнёра и переводится юристу только после выполнения этапа: подана претензия, получен ответ, подан иск.",
    ratingTitle: "Рейтинг по доказанным результатам",
    rating: "Рейтинг считается по реальным делам на платформе: сколько выиграно с поправкой на сложность, сколько денег возвращено, соблюдены ли сроки. Отзывы — только после сделки.",
    roadmapTitle: "Вы видите, где ваше дело",
    roadmap: "Дорожная карта: что уже сделано, что сейчас, какие шаги дальше и когда ожидать решения — лучший и худший вариант.",
    soon: "Безопасная сделка с юристом — в разработке",
    cta: "Посмотреть пример рейтинга",
  },
  lawyers: {
    title: "Юристы и адвокаты",
    subtitle: "Рейтинг по доказанным результатам на платформе, а не по рекламе.",
    score: "Рейтинг",
    confidence: { low: "мало дел", medium: "средняя выборка", high: "большая выборка" },
    vsBaseline: "к среднему по платформе",
    cases: "проверенных дел",
    recovered: "возвращено денег",
    onTime: "этапов в срок",
    reviews: "отзывы после сделки",
    from: "от",
    proBono: "бесплатно (pro bono)",
    response: "отвечает в среднем за",
    hours: "ч",
    years: "лет практики",
    verifiedLicense: "Лицензия проверена",
    verifiedId: "Личность подтверждена",
    success: "успех",
    platform: "в среднем",
    methodTitle: "Как считается рейтинг",
    method1: "Только дела, прошедшие через платформу: исход фиксируется при закрытии дела, а не со слов юриста.",
    method2: "Результат сравнивается со средним по той же категории дел — выбор лёгких дел не поднимает рейтинг.",
    method3: "Маленькая выборка подтягивается к среднему: 3 победы из 3 не обгонят 180 из 220.",
    method4: "Вес: результативность 45%, соблюдение сроков этапов 20%, доля возвращённых денег 20%, отзывы после сделки 15%.",
    choose: "Выбрать",
    chooseSoon: "Выбор юриста откроется вместе с безопасной сделкой",
  },
  landing: {
    promise: "Юридическая проблема → готовый документ → подача → контроль сроков → результат.",
    sub: "Опишите ситуацию своими словами. Konsilier.AI задаст несколько вопросов, подготовит документ, подскажет, куда его подать, и напомнит о сроках. Если досудебные шаги не помогут — передадим дело юристу.",
    startWeb: "Начать на сайте",
    startTelegram: "Открыть в Telegram",
    scenariosTitle: "Что уже умеем",
    howTitle: "Как это работает",
    how1: "Расскажите, что случилось",
    how2: "Ответьте на короткие вопросы и загрузите чеки или скриншоты",
    how3: "Получите документ и инструкцию по подаче",
    how4: "Мы следим за сроком ответа и предлагаем следующий шаг",
    countryTitle: "Ваша страна",
    countryLive: "Доступно",
    countrySoon: "Скоро",
    waitlistTitle: "Мы ещё не работаем в этой стране",
    waitlistText: "Оставьте контакт — напишем, когда запустимся.",
    waitlistContact: "E-mail или Telegram",
    waitlistProblem: "С какой проблемой вы столкнулись? (необязательно)",
    waitlistSend: "Сообщить о запуске",
    waitlistDone: "Спасибо! Мы напишем, когда запустимся.",
    price: "Стоимость",
    disclaimer: "Konsilier.AI не является адвокатом и не гарантирует результат. Заявителем всегда выступаете вы.",
  },
  start: {
    title: "Что случилось?",
    placeholder: "Например: купил телефон в интернет-магазине 12.08.2026 за 150 000 тенге, через неделю сломался, деньги не возвращают",
    submit: "Продолжить",
  },
  case: {
    back: "Все дела",
    send: "Ответить",
    more: "Дополнить описание",
    morePlaceholder: "Что именно купили или оформили, у кого, когда и на какую сумму, что пошло не так",
    skip: "Пропустить",
    upload: "Загрузить файл",
    uploadHint: "Фото или PDF, до 15 МБ",
    found: "Нашли в файле",
    confirm: "Всё верно",
    nothingFound: "Файл сохранён. Автоматически прочитать данные не удалось.",
    facts: "Данные дела",
    prepare: "Подготовить документ",
    handoff: "Передать юристу",
    awaitingApproval: "Документ проходит проверку юристом. Мы сообщим, когда он будет готов.",
    rejected: "Юрист вернул документ на доработку.",
    download: "Скачать",
    instructions: "Как подать",
    submitted: "Я отправил(а)",
    sendEmail: "Отправить по e-mail за меня",
    deadline: "Срок ответа",
    gotResponse: "Пришёл ответ",
    noResponse: "Ответа нет",
    responsePlaceholder: "Вставьте текст ответа",
    responseSend: "Проанализировать ответ",
    responseFile: "или загрузите файл ответа",
    close: "Закрыть дело",
    closeWon: "Вернули полностью",
    closePartial: "Частично",
    closeLost: "Не вернули",
    amountRecovered: "Сколько вернули",
    outcome: "Итог",
    days: "дней",
    response: "Ответ",
    notifications: "Уведомления",
    classes: { full: "Полностью", partial: "Частично", refusal: "Отказ", none: "Нет ответа" },
    deadlineStatus: { active: "идёт", met: "ответ получен", expired: "истёк", cancelled: "отменён" },
  },
  cases: { title: "Мои дела", empty: "Пока нет дел.", open: "Открыть" },
  admin: {
    title: "Админка",
    token: "Токен администратора",
    save: "Войти",
    needsReview: "Только needs_review",
    pendingApproval: "Ждут одобрения",
    all: "Все",
    approve: "Одобрить",
    reject: "Вернуть",
    note: "Комментарий юриста",
    preview: "Текст документа",
    audit: "Журнал",
    closeCase: "Закрыть дело",
    waitlist: "Лист ожидания",
    tick: "Прогнать напоминания",
  },
};

const kk: Dict = {
  nav: { start: "Бастау", cases: "Менің істерім" },
  landing: {
    startWeb: "Сайтта бастау",
    startTelegram: "Telegram-да ашу",
    countryTitle: "Сіздің еліңіз",
  },
  start: { title: "Не болды?", submit: "Жалғастыру" },
};

const dicts: Record<Lang, Dict> = { ru, kk };

function lookup(dict: Dict, key: string): string | undefined {
  let node: string | Dict | undefined = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "ru", setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ru");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("konsilier.lang");
      if (saved === "ru" || saved === "kk") setLangState(saved);
    } catch {}
  }, []);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("konsilier.lang", l);
    } catch {}
  };
  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang } = useLang();
  return (key: string) => lookup(dicts[lang], key) ?? lookup(dicts.ru, key) ?? key;
}
