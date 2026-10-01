import QRCode from "qrcode";

/** Owner 01.10 (referral П2): a 1080×1920 story card «Я знаю свои права» with the person's invitation link and its QR
 * code, drawn in the browser (nothing is sent anywhere). Returns a PNG. */
export async function storyCard(link: string, text: { title: string; line: string; offer: string; scan: string }): Promise<Blob> {
  const W = 1080, H = 1920;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d")!;
  const font = getComputedStyle(document.body).fontFamily || "sans-serif";

  const bg = g.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, "#0a6fe0");
  bg.addColorStop(1, "#003f8a");
  g.fillStyle = bg;
  g.fillRect(0, 0, W, H);

  const logo = await image("/icons/icon-512.png").catch(() => null);
  if (logo) {
    g.fillStyle = "#ffffff";
    round(g, 96, 150, 150, 150, 36); g.fill();
    g.drawImage(logo, 106, 160, 130, 130);
  }
  g.fillStyle = "#ffffff";
  g.font = `600 44px ${font}`;
  g.fillText("Konsiliér AI", 276, 245);

  g.font = `700 112px ${font}`;
  let y = wrap(g, text.title, 96, 470, W - 192, 124);
  g.font = `400 42px ${font}`;
  g.fillStyle = "rgba(255,255,255,0.88)";
  y = wrap(g, text.line, 96, y + 40, W - 192, 58);
  g.fillStyle = "#ffffff";
  g.font = `600 46px ${font}`;
  y = wrap(g, text.offer, 96, y + 40, W - 192, 62);

  // the QR code on a white card (as big as the space left allows), the scan hint inside, the short link under it
  const shown = link.replace(/^https?:\/\//, "").replace(/[?&]src=[^&]*/, "");
  const top = y + 30, bottomText = H - 90;
  const size = Math.max(320, Math.min(480, bottomText - 90 - top - 150));
  const x = (W - size) / 2;
  g.fillStyle = "#ffffff";
  round(g, x - 40, top, size + 80, size + 150, 40); g.fill();
  const qr = await image(await QRCode.toDataURL(link, { margin: 0, width: size, color: { dark: "#0b1b33", light: "#ffffff" } }));
  g.drawImage(qr, x, top + 40, size, size);
  g.fillStyle = "#0b1b33";
  g.font = `600 32px ${font}`;
  g.textAlign = "center";
  g.fillText(text.scan, W / 2, top + size + 105, size + 40);
  g.fillStyle = "#ffffff";
  g.font = `500 38px ${font}`;
  g.fillText(shown, W / 2, bottomText, W - 120);

  return new Promise((resolve, reject) => c.toBlob((b) => (b ? resolve(b) : reject(new Error("canvas"))), "image/png"));
}

function image(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = reject;
    i.src = src;
  });
}

function round(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

/** Draws wrapped text and returns the y after the last line. */
function wrap(g: CanvasRenderingContext2D, text: string, x: number, y: number, max: number, lh: number): number {
  let line = "";
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (g.measureText(next).width > max && line) { g.fillText(line, x, y); y += lh; line = word; } else line = next;
  }
  if (line) g.fillText(line, x, y);
  return y + lh;
}
