"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "ru" | "kk";

type Dict = { [key: string]: string | Dict };

const ru: Dict = {
  nav: { start: "Начать", cases: "Мои дела", admin: "Админка" },
  landing: {
    promise: "Юридическая проблема → готовый документ → подача → контроль сроков → результат.",
    sub: "Опишите ситуацию своими словами. Konsilier задаст несколько вопросов, подготовит документ, подскажет, куда его подать, и напомнит о сроках. Если досудебные шаги не помогут — передадим дело юристу.",
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
    disclaimer: "Konsilier не является адвокатом и не гарантирует результат. Заявителем всегда выступаете вы.",
  },
  start: {
    title: "Что случилось?",
    placeholder: "Например: купил телефон в интернет-магазине 12.08.2026 за 150 000 тенге, через неделю сломался, деньги не возвращают",
    submit: "Продолжить",
  },
  case: {
    back: "Все дела",
    send: "Ответить",
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
