"use client";

/** The first message typed on the home page, with its files, handed to the chat (/start) on the same page load:
 *  files cannot go through sessionStorage, and a client-side navigation keeps this module's memory. */
let pending: { text: string; files: File[] } | null = null;

export function handOff(text: string, files: File[]) {
  pending = { text, files };
  try { sessionStorage.setItem("konsilier.chat.draft", text); } catch {}  // a full reload still keeps the text
}

export function takeHandOff(): { text: string; files: File[] } | null {
  const out = pending;
  pending = null;
  return out;
}
