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
  pattern?: string | null;
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
  signatures?: DocSignature[];
  paid?: boolean;
  downloadable: boolean;
  submitted_at: string | null;
  response_class: string | null;
  response_label: string | null;
  response_summary: string | null;
  deadline: { due_date: string; status: string; norm_ref: string | null } | null;
  filing?: Filing | null;
  /** «Отправить по e-mail» through our service: may it go now (paid document, limits), and why not */
  email_send?: EmailSendState | null;
  /** what has been sent: e-mail with Resend's statuses, messengers with the client's screenshot */
  filings?: Delivery[];
  submitted_via?: string | null;
  /** Manual eOtinish bridge: what to pick on eotinish.kz (null → the step is not filed through eOtinish). */
  appeal_portal?: EotinishTarget | null;
  /** The filing record once the person entered the appeal number and date. */
  filed?: FilingRecord | null;
};

export type EmailSendState = { available: boolean; reason: string | null; left: number };
export type Delivery = {
  id: string;
  channel: "email" | "whatsapp" | "telegram" | "instagram" | "app_dispute" | "other";
  recipient: string;
  status: "sending" | "sent" | "delivered" | "bounced" | "complained" | "failed";
  has_receipt: boolean;
  replied_at?: string | null;  // a reply came to claims+<token>@… and is saved in the case
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string | null;
  doc_sha256: string;
  events: { at: string; type: string }[];
};
export type FoundContact = {
  kind: "email" | "phone" | "whatsapp" | "telegram" | "instagram" | "website" | "bin" | "address";
  value: string;
  sources: { type: "addressee" | "case" | "evidence" | "story"; label?: string; filename?: string }[];
};
/** One step of the route the server chose («Принцип 3 клика»): `auto` steps go by themselves on the one button. */
export type RouteStep = {
  /** `portal`: the official appeal portal of the pack (eOtinish in KZ) — the step opens the portal bridge */
  channel: "email" | "whatsapp" | "telegram" | "instagram" | "gov" | "portal" | "manual";
  to: string; auto: boolean; href?: string | null; reason?: string | null; done?: boolean;
  /** the portal's name for a `portal` step */
  portal?: string | null;
};
export type SendPlan = {
  contacts: FoundContact[]; message: string; email: EmailSendState; reply_to: string | null; filings: Delivery[];
  route: RouteStep[];
};
export type SendGo = {
  sent: Delivery[]; errors: { channel: string; to: string; code: string }[]; steps: RouteStep[]; message: string;
  case: CaseView;
};
export type EmailPreview = {
  from: string; to: string; reply_to: string; cc: string; subject: string; text: string;
  attachments: { name: string; size: number }[];
};

export type EotinishTarget = {
  channel: string;
  name: string;
  portal: string;
  body: string;
  body_key: string | null;
  recipient: string | null;
  appeal_type: "statement" | "complaint" | "proposal" | "request" | null;
  category: string | null;
  verified: boolean;
};
export type EotinishGuide = EotinishTarget & { text: string; has_pdf: boolean; filing: FilingRecord | null };
/** What was read from the portal's confirmation (POST .../portal-filing/proof); it is kept as the receipt. */
export type PortalProof = { evidence_id: string; number: string | null; filed_on: string | null; found: boolean; read_by: "text" | "model" | null };
export type FilingRecord = {
  id: string; channel: string; body: string; recipient: string; appeal_type: string | null; category: string | null;
  number: string; filed_at: string; receipt_evidence_id: string | null; doc_sha256: string | null;
  doc_format: string | null; source: string; created_at: string | null;
};

/** «Как подать»: everything comes from pack data; a null value is shown as «уточнит юрист». */
export type FilingTerm = { days: number; unit: "calendar" | "business"; norm_ref: string | null; verified: boolean };
export type Filing = {
  to: { name: string | null; address: string | null; email: string | null };
  response: FilingTerm | null;  // the term to answer, known before filing
  file_by: (FilingTerm & { date: string | null; since: string | null; overdue: boolean }) | null;
  ways: { kind: "in_person" | "post" | "online" | "email"; label: string; hint: string; url: string | null }[];
  online: { portal: string; url: string; phone: string[] | null; desktop: string[] | null; phone_ok: boolean } | null;
  signature: "handwritten" | "ecp" | "either" | null;
  signature_text: string | null;
};

export type Proposal = {
  type: "prepare_action" | "handoff" | "close" | "clarify" | "wait" | "none";
  action_id: string | null;
  title: string | null;
  response_class: string | null;
  suggested_result: string | null;
  message: string;
};

export type Plan = {
  document: string;
  addressee: string | null;
  channels: { kind: string; url: string | null }[];
  attachments: string[];
  lawyer_check: boolean;
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
    kind?: "dispute" | "service";
    beta?: boolean;  // experimental scenario (EXPERIMENTAL_SCENARIOS): marked «Бета»
    disclaimer?: string | null;
    price: { amount: number; currency: string };
  } | null;
  facts: { field: string; label: string; value: string }[];
  question: Question | null;
  evidence: { id: string; kind: string; filename: string; confirmed: boolean; extracted_facts: Record<string, string> }[];
  actions: CaseAction[];
  proposal: Proposal | null;
  roadmap: Roadmap | null;
  plan: Plan | null;
  payment: Payment | null;
  training_consent: boolean;
  /** While the case awaits an answer: the response deadline and the days left (negative once it has passed). */
  deadline: { due_date: string; status: string; days_left: number } | null;
  outcome: { result: string; amount_recovered: string | null; currency: string | null; days_to_resolution: number; resolved_at_step: string | null } | null;
  // admin only
  raw_facts?: Record<string, string>;
  audit?: { at: string; actor: string; event: string; from: string | null; to: string | null; data: Record<string, unknown> }[];
  initial_text?: string;
  qualification_confidence?: number | null;
};

/** Document payment by transfer (null when free). status "paid": the next document can be prepared now (the case
 *  plan, a subscription, a paid document or a referral bonus covers it); "none": choose one of `options`; otherwise the open bill. */
export type Payment = {
  amount: number;
  currency: string | null;
  status: "none" | "pending" | "awaiting_confirmation" | "not_found" | "paid";
  purpose: "document" | "case" | null;
  method: string;
  available: boolean;
  code: string | null;
  recipient_name: string | null;
  kaspi_phone: string | null;
  /** The open bill's id (for the /v1/invoices endpoints); null before a bill. */
  invoice_id?: number | null;
  /** Ways to pay switched on by the server (PAYMENT_METHODS); empty: the Kaspi transfer only, as before. */
  ways?: PayWay[];
  way?: PayWayId | null;
  payer_phone?: string | null;
  buyer?: { name: string; bin: string | null; address: string | null } | null;
  options: { purpose: "document" | "case"; amount: number }[];
  case_paid: boolean;
  /** The Kaspi Pay link bill was paid on trust: the document is given, the desk still matches the payment. */
  trusted?: boolean;
  /** A payment given on trust was not found: no new document until it is paid. */
  owed?: boolean;
  /** The last paid bill of the case (status is about the next document). */
  last_paid?: { code: string; amount: number; purpose: string; paid_at: string | null } | null;
  credits: number;
  bonus: number;  // referral bonus documents of the owner: they pay for the next document of any case
  /** Bonus account points of the owner (owner 02.10) and the points the open bill took (its amount is less by them). */
  bonus_balance?: number;
  bonus_used?: number;
  subscription: Subscription | null;
};

export type PayWayId = "kaspi_transfer" | "kaspi_link" | "kaspi_qr" | "kaspi_invoice" | "bank_invoice";
/** kaspi_link: url; kaspi_qr: image (and url); bank_invoice: seller. */
export type PayWay = { id: PayWayId; url?: string; image?: string; seller?: string };

export type Subscription = { plan: string; documents: number; left: number; ends_at: string };

/** /v1/plans: «Бизнес» subscriptions, the person's current period and open bill. */
export type PlansView = {
  plans: Record<string, { price: number; documents: number; days: number }>;
  case_price: number;
  currency: string;
  available: boolean;
  signed_in: boolean;
  subscription: Subscription | null;
  invoice: { id: number; code: string; purpose: string; plan: string | null; amount: number; currency: string | null;
    status: "pending" | "awaiting_confirmation" | "not_found" | "paid" | "cancelled";
    recipient_name: string | null; kaspi_phone: string | null } | null;
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
  why?: string | null;  // the system chose this recipient (owner 02.10): one line «почему»
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
  other_forums: ForumOption[];  // «Другой адресат» until the document is made
  upl_notice: string | null;
};

export type DocSignature = {
  id: string; role: string; signer_name: string | null; display: string; method: "ncalayer" | "egov";
  format: "pdf" | "docx"; signed_at: string;
};

export type AgreementView = {
  id: string; kind: string; title: string; status: "awaiting_customer" | "awaiting_lawyer" | "signed";
  template_reviewed: boolean; signatures: DocSignature[];
};
export type CaseLawyer = {
  lawyer: { name: string; kind: string; organization: string | null } | null;
  agreements: AgreementView[];
};

export type Identity = { kind: "email" | "phone" | "iin"; display: string; verified_at: string };
export type Me = { id: string; display_name: string | null; language: string; notify_email: boolean; identities: Identity[];
  bonus_documents: number;  // free documents for inviting a friend who paid (any case)
  bonus_balance?: number };  // bonus account points: they pay part of a document bill
export type AuthMethods = { email: boolean; phone: boolean; ecp: boolean; egov: boolean; google?: boolean; apple?: boolean };
export type SignedIn = { token: string; me: Me };

/** After a verified sign-in the account may be a different one (the identifier was already known). */
export function applySignIn(r: SignedIn): Me {
  localStorage.setItem("konsilier.token", r.token);
  signedIn = Promise.resolve(r.me.identities.length > 0);
  window.dispatchEvent(new Event(SIGNED_IN_EVENT));  // the app navigation drops its «Войти»
  import("@/lib/push").then((m) => m.resyncPush()).catch(() => {});  // this device's notifications follow the account
  return r.me;
}

export const SIGNED_IN_EVENT = "konsilier:signin";

let signedIn: Promise<boolean> | null = null;
/** Whether this device is signed in (a verified phone, e-mail or ЭЦП), not just an anonymous visitor. Never creates an
 *  account: without a token the answer is false at once. When the API is away, «signed in» is assumed (no nagging). */
export function isSignedIn(): Promise<boolean> {
  let token: string | null = null;
  try { token = localStorage.getItem("konsilier.token"); } catch {}
  if (!token) return Promise.resolve(false);
  signedIn ??= api<Me>("/v1/me").then((m) => m.identities.length > 0).catch(() => { signedIn = null; return true; });
  return signedIn;
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

// One anonymous account per browser: the first visit fires several requests at once (bell, cases, chat), and each
// must wait for the same account — otherwise a case opened with one token is asked for with another (404).
let creating: Promise<string> | null = null;

export async function ensureToken(): Promise<string> {
  const saved = typeof window !== "undefined" ? localStorage.getItem("konsilier.token") : null;
  if (saved) return saved;
  creating ??= (async () => {
    const r = await request(`${API_URL}/v1/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // who invited this person and where they came from (saved on arrival by captureReferral)
      body: JSON.stringify({ language: localStorage.getItem("konsilier.lang") ?? "ru",
        ref: localStorage.getItem("konsilier.ref"), src: localStorage.getItem("konsilier.src") }),
    });
    if (!r.ok) throw new ApiError(r.status, await r.text());
    const { token } = await r.json();
    localStorage.setItem("konsilier.token", token);
    return token as string;
  })().finally(() => { creating = null; });
  return creating;
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

/** Dictated audio → text (POST /v1/transcribe, free Gemini on the server; the audio is not stored). */
/** `partial`: the recording so far while the person is still speaking — the live text in the box. */
export async function transcribeAudio(audio: Blob, lang: string, filename = "voice.webm", partial = false): Promise<string> {
  const form = new FormData();
  form.append("file", audio, filename);
  form.append("lang", lang);
  if (partial) form.append("partial", "true");
  const r = await api<{ text: string }>("/v1/transcribe", { method: "POST", body: form });
  return r.text ?? "";
}

export async function fetchFile(path: string, extraHeaders?: Record<string, string>): Promise<Blob> {
  const headers = new Headers(extraHeaders);
  if (!extraHeaders) headers.set("Authorization", `Bearer ${await ensureToken()}`);
  const r = await request(`${API_URL}${path}`, { headers });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  return r.blob();
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadFile(path: string, filename: string, extraHeaders?: Record<string, string>) {
  saveBlob(await fetchFile(path, extraHeaders), filename);
}

/** Opens the browser's print dialog for a PDF (hidden frame; falls back to a new tab where frames can't print). */
export async function printFile(path: string) {
  const url = URL.createObjectURL(await fetchFile(path));
  const frame = document.createElement("iframe");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  frame.src = url;
  frame.onload = () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      window.open(url, "_blank");
    }
    setTimeout(() => { frame.remove(); URL.revokeObjectURL(url); }, 60_000);
  };
  document.body.appendChild(frame);
}

/** Save a document where the person chooses: the "Save as" dialog on a computer, the share sheet on a phone
 *  ("Save to Files"), a plain download elsewhere. */
export async function saveFileAs(path: string, filename: string): Promise<void> {
  const blob = await fetchFile(path);
  const w = window as Window & { showSaveFilePicker?: (o: unknown) => Promise<FileSystemFileHandle> };
  if (w.showSaveFilePicker) {
    try {
      const handle = await w.showSaveFilePicker({ suggestedName: filename });
      const writable = await (handle as FileSystemFileHandle & { createWritable: () => Promise<FileSystemWritableFileStream> }).createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return; // closed by the user
    }
  }
  const file = new File([blob], filename, { type: blob.type });
  const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
  if (nav.share && nav.canShare?.({ files: [file] }) && matchMedia("(pointer: coarse)").matches) {
    try {
      await nav.share({ files: [file] });
      return;
    } catch {
      return;
    }
  }
  saveBlob(blob, filename);
}

/** Share a document through the phone's share sheet (WhatsApp, Telegram, mail…); else just download it.
 *  Returns true when the share sheet was opened. */
export async function shareFile(path: string, filename: string, title: string): Promise<boolean> {
  const blob = await fetchFile(path);
  const file = new File([blob], filename, { type: blob.type || "application/pdf" });
  const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
  if (nav.share && nav.canShare?.({ files: [file] })) {
    try {
      await nav.share({ files: [file], title });
      return true;
    } catch {
      return false; // cancelled by the user
    }
  }
  saveBlob(blob, filename);
  return false;
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

/** First touch wins: remember ?ref= (invite code) and ?src= / utm_source (channel) until the account is created. */
export function captureReferral() {
  try {
    const q = new URLSearchParams(window.location.search);
    const ref = q.get("ref");
    const src = q.get("src") ?? q.get("utm_source");
    if (ref && !localStorage.getItem("konsilier.ref")) localStorage.setItem("konsilier.ref", ref.slice(0, 12));
    if (src && !localStorage.getItem("konsilier.src")) localStorage.setItem("konsilier.src", src.slice(0, 40));
  } catch {}
}
