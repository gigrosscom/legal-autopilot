"use client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Empty until the Telegram bot exists — then the "Open in Telegram" button appears.
export const TELEGRAM_BOT = process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "";

export type Question = {
  field: string;
  text: string;
  type: string;
  optional: boolean;
  evidence_kinds: { kind: string; label: string }[];
  uploaded?: number;
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
  stage: string;
  coverage: Coverage;
  safety: { hold_reason: string | null; hold_message: string | null; pending_ack: "false_report" | "special_category" | null };
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

export type ForumOption = {
  id: string;
  name: string;
  type: string;
  legal_effect: "binding" | "advisory" | "none";
  verified: boolean;
  channels: string[];
  deadline_known: boolean;
};

export type Emergency = { message: string; numbers: { label: string; number: string; verified?: boolean }[] };

export type Reply = {
  message: string;
  question: Question | null;
  intake_complete: boolean;
  error: string | null;
  options?: ForumOption[];
  ack_required?: "false_report" | "special_category" | null;
  emergency?: Emergency | null;
};

export type Coverage = {
  level: "verified" | "universal" | "lawyer";
  dispute: { id: string; title: string; branch: string } | null;
  forum: ForumOption | null;
  reasons: { code: string; label: string }[];
  options: ForumOption[];
  upl_notice: string | null;
};

export type Identity = { kind: "email" | "phone" | "iin"; display: string; verified_at: string };
export type Me = { id: string; display_name: string | null; language: string; identities: Identity[] };
export type AuthMethods = { email: boolean; phone: boolean; ecp: boolean; egov: boolean };
export type SignedIn = { token: string; me: Me };

/** After a verified sign-in the account may be a different one (the identifier was already known). */
export function applySignIn(r: SignedIn): Me {
  localStorage.setItem("konsilier.token", r.token);
  return r.me;
}

export class ApiError extends Error {
  /** Machine-readable reason from the API ({detail: {code}}), if any. */
  get code(): string | null {
    return typeof this.detail === "object" && this.detail && "code" in this.detail
      ? String((this.detail as { code: string }).code) : null;
  }

  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "object" && detail && "message" in detail ? String((detail as { message: string }).message) : String(detail));
  }
}

/** Thrown when there is no connection or the server did not answer in time. */
export class NetworkError extends Error {
  constructor(public kind: "offline" | "timeout") {
    super(kind);
  }
}

const ERRORS = {
  ru: {
    offline: "Нет интернета. Проверьте связь и попробуйте ещё раз — введённый текст сохранён.",
    timeout: "Сервер не ответил вовремя — возможно, медленная связь. Попробуйте ещё раз.",
    server: "Сервер временно не отвечает. Попробуйте ещё раз через минуту — введённый текст сохранён.",
    denied: "Нет доступа. Обновите страницу и попробуйте снова.",
    notFound: "Не найдено. Проверьте ссылку или откройте раздел «Мои дела».",
    tooMany: "Слишком много запросов. Подождите минуту и попробуйте снова.",
    invalid: "Проверьте введённые данные и попробуйте ещё раз.",
    unknown: "Что-то пошло не так. Обновите страницу и попробуйте ещё раз.",
  },
  kk: {
    offline: "Интернет жоқ. Байланысты тексеріп, қайта көріңіз — мәтін сақталды.",
    timeout: "Сервер уақытында жауап бермеді — байланыс баяу болуы мүмкін. Қайта көріңіз.",
    server: "Сервер уақытша жауап бермей тұр. Бір минуттан соң қайта көріңіз — мәтін сақталды.",
    denied: "Рұқсат жоқ. Бетті жаңартып, қайта көріңіз.",
    notFound: "Табылмады. Сілтемені тексеріңіз немесе «Істерім» бөлімін ашыңыз.",
    tooMany: "Сұрау тым көп. Бір минут күтіп, қайта көріңіз.",
    invalid: "Енгізген деректерді тексеріп, қайта көріңіз.",
    unknown: "Бірдеңе дұрыс болмады. Бетті жаңартып, қайта көріңіз.",
  },
  en: {
    offline: "No internet. Check your connection and try again — your text is saved.",
    timeout: "The server did not answer in time — the connection may be slow. Try again.",
    server: "The server is temporarily unavailable. Try again in a minute — your text is saved.",
    denied: "Access denied. Refresh the page and try again.",
    notFound: "Not found. Check the link or open “My cases”.",
    tooMany: "Too many requests. Wait a minute and try again.",
    invalid: "Check what you entered and try again.",
    unknown: "Something went wrong. Refresh the page and try again.",
  },
  ar: {
    offline: "لا يوجد اتصال بالإنترنت. تحقّق من الاتصال وحاول مرة أخرى — تم حفظ النص.",
    timeout: "لم يستجب الخادم في الوقت المحدد — قد يكون الاتصال بطيئًا. حاول مرة أخرى.",
    server: "الخادم غير متاح مؤقتًا. حاول بعد دقيقة — تم حفظ النص.",
    denied: "لا توجد صلاحية. حدّث الصفحة وحاول مرة أخرى.",
    notFound: "غير موجود. تحقّق من الرابط أو افتح «قضاياي».",
    tooMany: "طلبات كثيرة جدًا. انتظر دقيقة وحاول مرة أخرى.",
    invalid: "تحقّق من البيانات المدخلة وحاول مرة أخرى.",
    unknown: "حدث خطأ ما. حدّث الصفحة وحاول مرة أخرى.",
  },
  tr: {
    offline: "İnternet yok. Bağlantınızı kontrol edip tekrar deneyin — metniniz kaydedildi.",
    timeout: "Sunucu zamanında yanıt vermedi — bağlantı yavaş olabilir. Tekrar deneyin.",
    server: "Sunucu geçici olarak yanıt vermiyor. Bir dakika sonra tekrar deneyin — metniniz kaydedildi.",
    denied: "Erişim yok. Sayfayı yenileyip tekrar deneyin.",
    notFound: "Bulunamadı. Bağlantıyı kontrol edin veya “Dosyalarım” bölümünü açın.",
    tooMany: "Çok fazla istek. Bir dakika bekleyip tekrar deneyin.",
    invalid: "Girdiğiniz bilgileri kontrol edip tekrar deneyin.",
    unknown: "Bir şeyler ters gitti. Sayfayı yenileyip tekrar deneyin.",
  },
};

/** A message a person can understand, for any error from the API helpers, in the page language. */
export function errorText(e: unknown): string {
  const lang = typeof document !== "undefined" ? document.documentElement.lang : "ru";
  const m = ERRORS[lang as keyof typeof ERRORS] ?? ERRORS.ru;
  if (e instanceof NetworkError) return m[e.kind];
  if (e instanceof ApiError) {
    if (e.status >= 500) return m.server;
    if (e.status === 401 || e.status === 403) return m.denied;
    if (e.status === 404) return m.notFound;
    if (e.status === 429) return m.tooMany;
    const msg = e.message;
    if (msg && !msg.startsWith("[") && !msg.startsWith("{") && !msg.startsWith("<") && msg !== "[object Object]") return msg;
    return m.invalid;
  }
  return m.unknown;
}

// Slow phones and mobile networks: never hang forever. Answers that involve the AI can take up to a minute.
async function request(url: string, init: RequestInit = {}): Promise<Response> {
  const timeoutMs = (init.method ?? "GET") === "GET" ? 30_000 : 120_000;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch {
    throw new NetworkError(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "timeout");
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
