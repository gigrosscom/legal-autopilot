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
  outcome: { result: string; amount_recovered: string | null; currency: string | null; days_to_resolution: number; resolved_at_step: string | null } | null;
  // admin only
  raw_facts?: Record<string, string>;
  audit?: { at: string; actor: string; event: string; from: string | null; to: string | null; data: Record<string, unknown> }[];
  initial_text?: string;
  qualification_confidence?: number | null;
};

export type Reply = { message: string; question: Question | null; intake_complete: boolean; error: string | null };

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "object" && detail && "message" in detail ? String((detail as { message: string }).message) : String(detail));
  }
}

async function ensureToken(): Promise<string> {
  const saved = typeof window !== "undefined" ? localStorage.getItem("konsilier.token") : null;
  if (saved) return saved;
  const r = await fetch(`${API_URL}/v1/users`, {
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
  return handle<T>(await fetch(`${API_URL}${path}`, { ...init, headers }));
}

export async function downloadFile(path: string, filename: string, extraHeaders?: Record<string, string>) {
  const headers = new Headers(extraHeaders);
  if (!extraHeaders) headers.set("Authorization", `Bearer ${await ensureToken()}`);
  const r = await fetch(`${API_URL}${path}`, { headers });
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
  return handle<T>(await fetch(`${API_URL}${path}`, { ...init, headers }));
}

export async function adminApi<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Admin-Token", token);
  if (init.body) headers.set("Content-Type", "application/json");
  return handle<T>(await fetch(`${API_URL}${path}`, { ...init, headers }));
}
