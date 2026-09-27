"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/report";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => reportClientError(error), [error]);
  return (
    <div className="card mx-auto max-w-lg space-y-3 text-center">
      <h1 className="text-xl font-bold">Что-то пошло не так</h1>
      <p className="text-sm text-ink/70">
        Ваши данные сохранены — дело не потеряно. Мы получили отчёт об ошибке. Обновите страницу, чтобы продолжить.
      </p>
      <p className="text-xs text-ink/50">
        Если включён автоперевод страницы в браузере, отключите его для этого сайта.
      </p>
      <div className="flex justify-center gap-2">
        <button className="btn-primary" onClick={() => window.location.reload()}>Обновить страницу</button>
        <button className="btn-ghost" onClick={() => reset()}>Попробовать снова</button>
      </div>
    </div>
  );
}
