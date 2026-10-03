import { API_URL } from "./api";

/** Send a client-side crash to the API logs (best effort, never throws). */
export function reportClientError(error: Error & { digest?: string }) {
  try {
    const body = JSON.stringify({
      message: String(error?.message ?? error).slice(0, 1000),
      stack: String(error?.stack ?? "").slice(0, 4000),
      digest: error?.digest ?? null,
      url: typeof window !== "undefined" ? window.location.pathname : null,
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent.slice(0, 300) : null,
      translated: typeof document !== "undefined"
        ? document.documentElement.className.includes("translated") : null,
    });
    fetch(`${API_URL}/v1/client-errors`, { method: "POST", headers: { "Content-Type": "application/json" }, body,
      keepalive: true }).catch(() => {});
  } catch {}
}
