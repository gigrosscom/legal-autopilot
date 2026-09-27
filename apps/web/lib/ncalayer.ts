"use client";

// NCALayer: the official desktop app that gives the browser access to the user's ЭЦП keys.
// It listens on wss://127.0.0.1:13579; the "kz.gov.pki.knca.basics" module signs data as CMS.

export class NcaLayerError extends Error {
  constructor(public kind: "not_running" | "cancelled" | "failed") {
    super(kind);
  }
}

const URL = "wss://127.0.0.1:13579/";

/** Sign base64 `data` with an authentication key; returns the CMS (base64) with the data attached. */
export function signForAuth(dataB64: string, locale: string, timeoutMs = 180_000): Promise<string> {
  return new Promise((resolve, reject) => {
    let ws: WebSocket;
    try {
      ws = new WebSocket(URL);
    } catch {
      reject(new NcaLayerError("not_running"));
      return;
    }
    let opened = false;
    const timer = setTimeout(() => {
      ws.close();
      reject(new NcaLayerError("cancelled"));
    }, timeoutMs);
    const done = (fn: () => void) => {
      clearTimeout(timer);
      fn();
      ws.close();
    };
    ws.onerror = () => done(() => reject(new NcaLayerError(opened ? "failed" : "not_running")));
    ws.onopen = () => {
      opened = true;
      ws.send(JSON.stringify({
        module: "kz.gov.pki.knca.basics",
        method: "sign",
        args: {
          allowedStorages: ["PKCS12", "AKKaztokenStore", "AKKZIDCardStore", "AKEToken72KStore", "AKJaCartaStore"],
          format: "cms",
          data: dataB64,
          signingParams: { decode: true, encapsulate: true, digested: false, tsaProfile: {} },
          // authentication certificates only (client auth EKU)
          signerParams: { extKeyUsageOids: ["1.3.6.1.5.5.7.3.2"] },
          locale: ["kk", "ru", "en"].includes(locale) ? locale : "ru",
        },
      }));
    };
    ws.onmessage = (ev) => {
      let msg: { status?: boolean; body?: { result?: string[] | string }; code?: string };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.status === true && msg.body?.result) {
        const r = msg.body.result;
        done(() => resolve(Array.isArray(r) ? r[0] : r));
      } else if (msg.status === false || msg.code) {
        done(() => reject(new NcaLayerError("cancelled")));
      }
      // other messages (e.g. version handshake) are ignored
    };
  });
}
