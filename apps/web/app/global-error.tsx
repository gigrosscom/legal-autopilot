"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/report";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => reportClientError(error), [error]);
  return (
    <html lang="ru" translate="no">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#f7f4ee", color: "#14213d", padding: 32 }}>
        <div style={{ maxWidth: 480, margin: "10vh auto", textAlign: "center" }}>
          <h1>Что-то пошло не так</h1>
          <p>Ваши данные сохранены — дело не потеряно. Обновите страницу, чтобы продолжить.</p>
          <button onClick={() => window.location.reload()} style={{ padding: "10px 18px", borderRadius: 12 }}>
            Обновить страницу
          </button>
        </div>
      </body>
    </html>
  );
}
