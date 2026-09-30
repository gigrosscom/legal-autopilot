"use client";

import { API_URL, ApiError, api, ensureToken } from "@/lib/api";

export type ChatNorm = { act: string; act_code: string; article: string; title: string; url: string };
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  created_at: string;
  attachments: { id: string; filename: string }[];
  norms: ChatNorm[];
  offer_document?: boolean;  // the reply offers to prepare the document: a button shows under it
};
export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool"; name: string }
  // limit/remaining: the free daily limit (a rolling 24-hour window) and what is left of it after this message
  | { type: "done"; message: ChatMessage; limit?: number; remaining?: number }
  | { type: "error"; code: string; message: string };

export const chatHistory = (caseId: string) => api<ChatMessage[]>(`/v1/cases/${caseId}/chat`);

/** Send a message and read the streamed reply (server-sent events) chunk by chunk. */
export async function sendChat(caseId: string, text: string, attachments: string[], onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal) {
  const token = await ensureToken();
  const r = await fetch(`${API_URL}/v1/cases/${caseId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ text, attachments }),
    signal,
  });
  if (!r.ok || !r.body) {
    let detail: unknown = r.statusText;
    try { detail = (await r.json()).detail; } catch {}
    throw new ApiError(r.status, detail);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 2);
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
    }
  }
}
