"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/report";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => reportClientError(error), [error]);
  return (
    <html lang="ru" translate="no">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#ffffff", color: "#0b172a", padding: 32 }}>
        <div style={{ maxWidth: 480, margin: "10vh auto", textAlign: "center" }}>
          {/* No language context here (the root layout crashed), so both languages, short. */}
          <h1>Что-то пошло не так · Бірдеңе дұрыс болмады</h1>
          <p>Ваши данные сохранены. Обновите страницу.</p>
          <p>Деректеріңіз сақталды. Бетті жаңартыңыз.</p>
          <button onClick={() => window.location.reload()} style={{ padding: "10px 18px", borderRadius: 12 }}>
            Обновить · Жаңарту
          </button>
        </div>
      </body>
    </html>
  );
}
