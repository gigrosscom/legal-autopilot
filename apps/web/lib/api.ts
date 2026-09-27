"use client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const TELEGRAM_BOT = process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "konsilier_bot";

export type Question = {
  field: string;
  text: string;
  type: string;
  optional: boolean;
  evidence_kinds: { kind: string; label: string }[];
};

export type CaseAction = {
  id: string;
  action_id: string;
  sequence: number;
  kind: string;
  title: string;
  status: string;
  approval_status: string;
  approval_note: string | null;
  email_allowed: boolean;
  addressee: { name?: string; email?: string | null; submit_url?: string | null; kind?: string };
  instructions: string[];
  has_docx: boolean;
  has_pdf: boolean;
  downloadable: boolean;
  submitted_at: string | null;
  response_class: string | null;
  response_label: string | null;
  response_summary: string | null;
  deadline: { due_date: string; status: string; norm_ref: string | null } | null;
};

export type Proposal = {
  type: "prepare_action" | "handoff" | "close" | "clarify" | "wait" | "none";
  action_id: string | null;
  title: string | null;
  response_class: string | null;
  suggested_result: string | null;
  message: string;
};

export type CaseView = {
  id: string;
  status: string;
  status_label: string;
  needs_review: boolean;
  jurisdiction: string | null;
  language: string;
  amount_at_stake: string | null;
  currency: string | null;
  created_at: string;
  ai_label: string;
  service_disclaimer: string;
  scenario: {
    id: string;
    version: string;
    title: string;
    draft: boolean;
    draft_disclaimer: string | null;
    price: { amount: number; currency: string };
  } | null;
  facts: { field: string; label: string; value: string }[];
  question: Question | null;
  evidence: { id: string; kind: string; filename: string; confirmed: boolean; extracted_facts: Record<string, string> }[];
  actions: CaseAction[];
  proposal: Proposal | null;
  roadmap: Roadmap | null;
  outcome: { result: string; amount_recovered: string | null; currency: string | null; days_to_resolution: number; resolved_at_step: string | null } | null;
  // admin only
  raw_facts?: Record<string, string>;
  audit?: { at: string; actor: string; event: string; from: string | null; to: string | null; data: Record<string, unknown> }[];
  initial_text?: string;
  qualification_confidence?: number | null;
};

export type RoadmapStep = {
  key: string;
  kind: "intake" | "document" | "handoff" | "resolution";
  title: string;
  status: "done" | "current" | "upcoming" | "skipped";
  conditional: boolean;
  started_on: string | null;
  finished_on: string | null;
  due_on: string | null;
  estimated_on: string | null;
  detail: string;
  norm_ref: string | null;
};

export type Roadmap = {
  steps: RoadmapStep[];
  best_case_on: string | null;
  worst_case_on: string | null;
  open_ended_after_worst: boolean;
};

export type Reply = { message: string; question: Question | null; intake_complete: boolean; error: string | null };

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "object" && detail && "message" in detail ? String((detail as { message: string }).message) : String(detail));
  }
}

/** Thrown when there is no connection or the server did not answer in time. */
export class NetworkError extends Error {}

/** A message a person can understand, for any error from the API helpers. */
export function errorText(e: unknown): string {
  if (e instanceof NetworkError) return e.message;
  if (e instanceof ApiError) {
    if (e.status >= 500) return "Сервер временно не отвечает. Попробуйте ещё раз через минуту — введённый текст сохранён.";
    if (e.status === 401 || e.status === 403) return "Нет доступа. Обновите страницу и попробуйте снова.";
    if (e.status === 404) return "Не найдено. Проверьте ссылку или откройте раздел «Мои дела».";
    if (e.status === 429) return "Слишком много запросов. Подождите минуту и попробуйте снова.";
    const msg = e.message;
    if (msg && !msg.startsWith("[") && !msg.startsWith("{") && !msg.startsWith("<") && msg !== "[object Object]") return msg;
    return "Проверьте введённые данные и попробуйте ещё раз.";
  }
  return "Что-то пошло не так. Обновите страницу и попробуйте ещё раз.";
}

// Slow phones and mobile networks: never hang forever. Answers that involve the AI can take up to a minute.
async function request(url: string, init: RequestInit = {}): Promise<Response> {
  const timeoutMs = (init.method ?? "GET") === "GET" ? 30_000 : 120_000;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch {
    throw new NetworkError(
      typeof navigator !== "undefined" && !navigator.onLine
        ? "Нет интернета. Проверьте связь и попробуйте ещё раз — введённый текст сохранён."
        : "Сервер не ответил вовремя — возможно, медленная связь. Попробуйте ещё раз.",
    );
  } finally {
    clearTimeout(timer);
  }
}

async function ensureToken(): Promise<string> {
  const saved = typeof window !== "undefined" ? localStorage.getItem("konsilier.token") : null;
  if (saved) return saved;
  const r = await request(`${API_URL}/v1/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: localStorage.getItem("konsilier.lang") ?? "ru" }),
  });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  const { token } = await r.json();
  localStorage.setItem("konsilier.token", token);
  return token;
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail: unknown = await r.text();
    try {
      detail = JSON.parse(detail as string).detail;
    } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await ensureToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return handle<T>(await request(`${API_URL}${path}`, { ...init, headers }));
}

export async function downloadFile(path: string, filename: string, extraHeaders?: Record<string, string>) {
  const headers = new Headers(extraHeaders);
  if (!extraHeaders) headers.set("Authorization", `Bearer ${await ensureToken()}`);
  const r = await request(`${API_URL}${path}`, { headers });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  return handle<T>(await request(`${API_URL}${path}`, { ...init, headers }));
}

export async function adminApi<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Admin-Token", token);
  if (init.body) headers.set("Content-Type", "application/json");
  return handle<T>(await request(`${API_URL}${path}`, { ...init, headers }));
}
