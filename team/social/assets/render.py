"""Render Instagram start assets for Konsiliér AI from team/social/instagram-start.md.

Outputs (paths relative to team/social/assets/):
  instagram/ig-NN/01.png ...        carousel slides, 1080x1440 (3:4)
  instagram/ig-NN/reel.mp4, cover.png  text-only Reels, 1080x1920, no audio
  instagram/highlights/s-0N.png, cover-N.png  stories and highlight covers, 1080x1920
  avatar-1080.png, facebook-cover-1702x630.png, linkedin-cover-1512x256.png,
  linkedin-logo-400.png, youtube-banner-2560x1440.png

Usage: pip install pillow imageio-ffmpeg && python team/social/assets/render.py
The source of truth for all texts is instagram-start.md; edit the tables there and re-run.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "instagram-start.md"
FONT_DIR = HERE / "fonts"
FONT_PATH = FONT_DIR / "Inter.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"

# Brand tokens (apps/web/app/globals.css)
WHITE = "#ffffff"
NAVY = "#0e2a5a"
INK = "#0b172a"
ACCENT = "#8796b5"
MUTED = "#556174"
LINE = "#e2e7ee"
FADED = "#a9b3c4"

# K mark geometry measured from apps/web/public/icons/icon-512.png (512 px space)
K_BOX = (149, 128, 385, 385)
K_BAR = [(149, 128), (205, 128), (205, 385), (149, 385)]
K_UPPER = [(302, 171), (380, 171), (303, 249), (229, 249)]
K_LOWER = [(228, 267), (303, 267), (385, 385), (310, 385)]


# ---------- fonts ----------

def ensure_font() -> None:
    if FONT_PATH.exists():
        return
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    print("downloading Inter (OFL) ...")
    urllib.request.urlretrieve(FONT_URL, FONT_PATH)


_font_cache: dict[tuple[int, int], ImageFont.FreeTypeFont] = {}


def font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    key = (size, weight)
    if key not in _font_cache:
        f = ImageFont.truetype(str(FONT_PATH), size)
        try:
            f.set_variation_by_axes([min(32, max(14, size / 2)), weight])
        except Exception:
            pass
        _font_cache[key] = f
    return _font_cache[key]


# ---------- drawing helpers ----------

def draw_k(d: ImageDraw.ImageDraw, x: float, y: float, h: float, dark: str, accent: str) -> float:
    """Draw the K mark with its top-left at (x, y) and height h. Returns width."""
    x0, y0, x1, y1 = K_BOX
    s = h / (y1 - y0)

    def tr(pts):
        return [(x + (px - x0) * s, y + (py - y0) * s) for px, py in pts]

    d.polygon(tr(K_BAR), fill=dark)
    d.polygon(tr(K_UPPER), fill=dark)
    d.polygon(tr(K_LOWER), fill=accent)
    return (x1 - x0) * s


def accent_bar(d: ImageDraw.ImageDraw, x: float, y: float, w: float = 132, h: float = 14, color: str = ACCENT) -> None:
    """Parallelogram echoing the lower arm of K."""
    slant = h * 0.9
    d.polygon([(x, y), (x + w - slant, y), (x + w, y + h), (x + slant, y + h)], fill=color)


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    # split on plain spaces only: non-breaking spaces keep "1 990 ₸" together
    words = [w for w in nbsp(text).split(" ") if w]
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_block(d, x, y, text, f, fill, width, spacing=1.18, align="left", cx=None) -> float:
    """Draw wrapped text; returns new y."""
    for line in wrap(text, f, width):
        if align == "center":
            lx = cx - f.getlength(line) / 2
        else:
            lx = x
        d.text((lx, y), line, font=f, fill=fill)
        y += f.size * spacing
    return y


def block_height(text, f, width, spacing=1.18) -> float:
    return len(wrap(text, f, width)) * f.size * spacing


def header(d, w, dark: bool, counter: str | None, top=72, side=96) -> None:
    kh = 52
    kw = draw_k(d, side, top, kh, WHITE if dark else INK, ACCENT)
    d.text((side + kw + 18, top + 8), "Konsiliér AI", font=font(30, 600), fill=WHITE if dark else INK)
    if counter:
        f = font(28, 500)
        d.text((w - side - f.getlength(counter), top + 10), counter, font=f, fill=ACCENT)


def footer(d, w, h, dark: bool, side=96, text="konsilier.com") -> None:
    f = font(28, 500)
    d.line([(side, h - 128), (w - side, h - 128)], fill=("#27406e" if dark else LINE), width=2)
    d.text((side, h - 100), text, font=f, fill=ACCENT if dark else MUTED)


# ---------- markdown parsing ----------

def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_posts(md: str) -> list[dict]:
    posts = []
    sections = re.split(r"^### (IG-\d\d) — ", md, flags=re.M)
    for i in range(1, len(sections), 2):
        pid, body = sections[i], sections[i + 1]
        kind = "reel" if body.lstrip().lower().startswith("reels") else "carousel"
        rows = []
        lines = body.splitlines()
        for j, line in enumerate(lines):
            if line.startswith("| №") and "Фон" in line:
                cols = split_row(line)
                k = j + 2
                while k < len(lines) and lines[k].startswith("|"):
                    cells = split_row(lines[k])
                    rows.append(dict(zip(cols, cells)))
                    k += 1
                break
        posts.append({"id": pid, "kind": kind, "rows": rows})
    return posts


def parse_stories(md: str) -> list[dict]:
    out = []
    for line in md.splitlines():
        m = re.match(r"^\| (S-0\d) \| (.+?) \| (.+?) \| .+\|$", line)
        if m:
            out.append({"id": m.group(1), "ru": m.group(2).split(" · "), "kk": m.group(3).split(" · ")})
    return out


def nbsp(text: str) -> str:
    """Keep prices and short words together: "1 990 ₸" never breaks."""
    text = re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", text)
    text = re.sub(r"(\d) ₸", "\\1\u00a0₸", text)
    return text


def items(cell: str) -> list[str]:
    return [nbsp(x.strip()) for x in cell.split("<br>") if x.strip()]


# ---------- carousel ----------

W, H = 1080, 1440
SIDE = 96
CONTENT_W = W - 2 * SIDE


def slide_cover(row, n, total, dark: bool) -> Image.Image:
    bg = NAVY if dark else WHITE
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    # large decorative K, partly cut by the bottom-right edge
    if dark:
        draw_k(d, W - 400, H - 620, 700, "#15356b", "#3a5586")
    else:
        draw_k(d, W - 400, H - 620, 700, "#f1f4f8", "#e2e7ee")
    header(d, W, dark, f"{n}/{total}")
    title_c = WHITE if dark else NAVY
    kk_c = ACCENT if dark else MUTED
    for size in (88, 80, 72, 64):
        tf, kf = font(size, 700), font(int(size * 0.5), 500)
        hgt = block_height(row["Заголовок ru"], tf, CONTENT_W, 1.12) + 28 + block_height(row["Заголовок kk"], kf, CONTENT_W)
        if hgt < 760:
            break
    y = 300
    y = text_block(d, SIDE, y, row["Заголовок ru"], tf, title_c, CONTENT_W, 1.12)
    y += 28
    y = text_block(d, SIDE, y, row["Заголовок kk"], kf, kk_c, CONTENT_W)
    y += 40
    accent_bar(d, SIDE, y)
    # subtitle near bottom
    sf, skf = font(36, 600), font(28, 500)
    ys = H - 330
    ys = text_block(d, SIDE, ys, nbsp(row["Текст ru"]), sf, WHITE if dark else INK, 560)
    text_block(d, SIDE, ys + 6, nbsp(row["Текст kk"]), skf, kk_c, 560)
    footer(d, W, H, dark)
    return im


def slide_content(row, n, total) -> Image.Image:
    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    header(d, W, False, f"{n}/{total}")
    ru_items, kk_items = items(row["Текст ru"]), items(row["Текст kk"])
    for tsize, isize in ((80, 54), (74, 50), (68, 46), (62, 42), (56, 38), (52, 34), (48, 30)):
        tf, tkf = font(tsize, 700), font(int(tsize * 0.55), 500)
        f_ru, f_kk = font(isize, 600), font(int(isize * 0.74), 450)
        head_h = block_height(row["Заголовок ru"], tf, CONTENT_W, 1.12) + 16 + block_height(row["Заголовок kk"], tkf, CONTENT_W) + 70
        body_h = sum(block_height(r, f_ru, CONTENT_W) + 10 + block_height(k, f_kk, CONTENT_W) + 62
                     for r, k in zip(ru_items, kk_items))
        if head_h + body_h < H - 230 - 170:
            break
    y = 230
    y = text_block(d, SIDE, y, row["Заголовок ru"], tf, NAVY, CONTENT_W, 1.12)
    y += 16
    y = text_block(d, SIDE, y, row["Заголовок kk"], tkf, MUTED, CONTENT_W)
    y += 32
    accent_bar(d, SIDE, y)
    y += 14 + 48
    for idx, (r, k) in enumerate(zip(ru_items, kk_items)):
        if idx:
            d.line([(SIDE, y - 30), (W - SIDE, y - 30)], fill=LINE, width=2)
        y = text_block(d, SIDE, y, r, f_ru, INK, CONTENT_W)
        y += 10
        y = text_block(d, SIDE, y, k, f_kk, MUTED, CONTENT_W)
        y += 62
    footer(d, W, H, False)
    return im


def slide_cta(row, n, total) -> Image.Image:
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    header(d, W, True, f"{n}/{total}")
    cx = W / 2
    draw_k(d, cx - 118 * 0.62, 400, 160, WHITE, ACCENT)
    y = 640
    y = text_block(d, 0, y, row["Заголовок ru"], font(64, 700), WHITE, CONTENT_W, 1.12, "center", cx)
    y += 14
    y = text_block(d, 0, y, row["Заголовок kk"], font(36, 500), ACCENT, CONTENT_W, 1.18, "center", cx)
    y += 44
    accent_bar(d, cx - 66, y)
    y += 70
    for r, k in zip(items(row["Текст ru"]), items(row["Текст kk"])):
        y = text_block(d, 0, y, r, font(38, 600), WHITE, CONTENT_W, 1.18, "center", cx)
        y = text_block(d, 0, y + 4, k, font(29, 450), ACCENT, CONTENT_W, 1.18, "center", cx)
        y += 30
    footer(d, W, H, True, text="Konsiliér AI — ИИ-помощник по правовым вопросам")
    return im


def render_carousel(post: dict, out: Path) -> None:
    rows = post["rows"]
    total = len(rows)
    out.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(rows, 1):
        dark = row["Фон"].startswith("тём")
        if i == 1:
            im = slide_cover(row, i, total, dark)
        elif i == total and dark:
            im = slide_cta(row, i, total)
        else:
            im = slide_content(row, i, total)
        im.save(out / f"{i:02d}.png", optimize=True)


# ---------- reels ----------

RW, RH = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 300, 1580  # keep text inside the centre 3:4 zone and above the caption overlay


def reel_frame(row, first_or_last: bool) -> Image.Image:
    dark = row["Фон"].startswith("тём")
    bg = NAVY if dark else WHITE
    im = Image.new("RGB", (RW, RH), bg)
    d = ImageDraw.Draw(im)
    cx = RW / 2
    title_c = WHITE if dark else NAVY
    kk_c = ACCENT if dark else MUTED
    kh = 96
    draw_k(d, cx - 236 / 257 * kh / 2, SAFE_TOP + 20, kh, WHITE if dark else INK, ACCENT)
    if first_or_last:
        y = 620
        y = text_block(d, 0, y, row["Заголовок ru"], font(84, 700), title_c, RW - 2 * SIDE, 1.1, "center", cx)
        y += 18
        y = text_block(d, 0, y, row["Заголовок kk"], font(44, 500), kk_c, RW - 2 * SIDE, 1.18, "center", cx)
        y += 50
        accent_bar(d, cx - 66, y)
        y += 80
        for r, k in zip(items(row["Текст ru"]), items(row["Текст kk"])):
            y = text_block(d, 0, y, r, font(46, 600), WHITE if dark else INK, RW - 2 * SIDE, 1.18, "center", cx)
            y = text_block(d, 0, y + 4, k, font(34, 450), kk_c, RW - 2 * SIDE, 1.18, "center", cx)
            y += 34
    else:
        y = SAFE_TOP + 170
        y = text_block(d, SIDE, y, row["Заголовок ru"], font(64, 700), NAVY, RW - 2 * SIDE, 1.1)
        y = text_block(d, SIDE, y + 6, row["Заголовок kk"], font(36, 500), MUTED, RW - 2 * SIDE)
        y += 26
        accent_bar(d, SIDE, y)
        y += 70
        ru_items, kk_items = items(row["Текст ru"]), items(row["Текст kk"])
        n = len(ru_items)
        for isize in (46, 42, 38, 35):
            f_ru, f_kk = font(isize, 600), font(int(isize * 0.74), 450)
            need = sum(block_height(r, f_ru, RW - 2 * SIDE - 80) + block_height(k, f_kk, RW - 2 * SIDE - 80) + 44
                       for r, k in zip(ru_items, kk_items))
            if y + need < SAFE_BOTTOM:
                break
        for idx, (r, k) in enumerate(zip(ru_items, kk_items)):
            current = idx == n - 1
            num_c = ACCENT
            ru_c = INK if current else FADED
            kk_c2 = MUTED if current else "#c3cad6"
            d.text((SIDE, y), f"{idx + 1}", font=font(isize, 700), fill=num_c)
            yy = text_block(d, SIDE + 80, y, r, f_ru, ru_c, RW - 2 * SIDE - 80)
            yy = text_block(d, SIDE + 80, yy + 4, k, f_kk, kk_c2, RW - 2 * SIDE - 80)
            y = yy + 40
    f = font(30, 500)
    label = "konsilier.com"
    d.text((cx - f.getlength(label) / 2, SAFE_BOTTOM + 10), label, font=f, fill=ACCENT if dark else MUTED)
    return im


def parse_secs(s: str) -> float:
    a, b = s.replace("–", "-").split("-")
    return float(b) - float(a)


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def render_reel(post: dict, out: Path) -> None:
    rows = post["rows"]
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        concat = []
        for i, row in enumerate(rows):
            im = reel_frame(row, i in (0, len(rows) - 1))
            p = tmp / f"f{i:02d}.png"
            im.save(p)
            if i == 0:
                # grid cover: centre 3:4 crop is what the profile grid shows
                im.save(out / "cover.png", optimize=True)
            concat.append(f"file '{p}'\nduration {parse_secs(row['Сек'])}")
        concat.append(f"file '{tmp / f'f{len(rows) - 1:02d}.png'}'")
        lst = tmp / "list.txt"
        lst.write_text("\n".join(concat) + "\n")
        cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
               "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-movflags", "+faststart", str(out / "reel.mp4")]
        subprocess.run(cmd, check=True)


# ---------- highlights ----------

def render_story(story: dict, out: Path) -> None:
    im = Image.new("RGB", (RW, RH), WHITE)
    d = ImageDraw.Draw(im)
    header(d, RW, False, None, top=SAFE_TOP - 120)
    y = SAFE_TOP + 60
    y = text_block(d, SIDE, y, story["ru"][0], font(64, 700), NAVY, RW - 2 * SIDE, 1.1)
    y = text_block(d, SIDE, y + 6, story["kk"][0], font(36, 500), MUTED, RW - 2 * SIDE)
    y += 26
    accent_bar(d, SIDE, y)
    y += 70
    rest = list(zip(story["ru"][1:], story["kk"][1:]))
    isize = 42 if len(rest) <= 4 else 36
    for r, k in rest:
        y = text_block(d, SIDE, y, r, font(isize, 600), INK, RW - 2 * SIDE)
        y = text_block(d, SIDE, y + 4, k, font(int(isize * 0.74), 450), MUTED, RW - 2 * SIDE)
        y += 34
    f = font(30, 500)
    d.text((SIDE, SAFE_BOTTOM + 60), "konsilier.com", font=f, fill=MUTED)
    im.save(out / f"{story['id'].lower()}.png", optimize=True)


def render_highlight_cover(n: int, glyph: str, out: Path) -> None:
    im = Image.new("RGB", (RW, RH), NAVY)
    d = ImageDraw.Draw(im)
    size = 300 if len(glyph) <= 2 else 220
    f = font(size, 700)
    bbox = d.textbbox((0, 0), glyph, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((RW / 2 - w / 2 - bbox[0], RH / 2 - h / 2 - bbox[1]), glyph, font=f, fill=WHITE)
    im.save(out / f"cover-{n}.png", optimize=True)


# ---------- avatar and covers ----------

def render_brand(out: Path) -> None:
    # avatar: K centred, ~50% of the canvas so a circle crop never touches it
    im = Image.new("RGB", (1080, 1080), WHITE)
    d = ImageDraw.Draw(im)
    kh = 540
    kw = 236 / 257 * kh
    draw_k(d, 540 - kw / 2, 540 - kh / 2, kh, INK, ACCENT)
    im.save(out / "avatar-1080.png", optimize=True)
    im.resize((400, 400), Image.LANCZOS).save(out / "linkedin-logo-400.png", optimize=True)

    def cover(w, h, safe_w, safe_h, name):
        im = Image.new("RGB", (w, h), WHITE)
        d = ImageDraw.Draw(im)
        cx, cy = w / 2, h / 2
        s = safe_h / 3.2
        ru, kk = "Сначала понять. Потом действовать.", "Алдымен түсін. Сосын әрекет ет."
        fr, fk = font(int(s * 0.95), 700), font(int(s * 0.55), 500)
        while fr.getlength(ru) > safe_w * 0.92:
            fr, fk = font(fr.size - 2, 700), font(int((fr.size - 2) * 0.58), 500)
        total = fr.size * 1.25 + fk.size * 1.45 + fr.size * 0.16
        y = cy - total / 2
        d.text((cx - fr.getlength(ru) / 2, y), ru, font=fr, fill=NAVY)
        d.text((cx - fk.getlength(kk) / 2, y + fr.size * 1.25), kk, font=fk, fill=MUTED)
        bw, bh = fr.size * 1.6, max(4, fr.size * 0.16)
        accent_bar(d, cx - bw / 2, y + fr.size * 1.25 + fk.size * 1.45, bw, bh)
        im.save(out / name, optimize=True)

    cover(1702, 630, 1100, 400, "facebook-cover-1702x630.png")  # 2x of 851x315 (Facebook Help)
    cover(1512, 256, 900, 150, "linkedin-cover-1512x256.png")  # LinkedIn Help a563309
    cover(2560, 1440, 1544, 422, "youtube-banner-2560x1440.png")  # safe area 1235x338 at 2048 -> x1.25


# ---------- main ----------

def main() -> int:
    ensure_font()
    md = SOURCE.read_text(encoding="utf-8")
    ig = HERE / "instagram"
    posts = parse_posts(md)
    for p in posts:
        out = ig / p["id"].lower()
        if not p["rows"]:
            print(f"{p['id']}: no table found", file=sys.stderr)
            continue
        if p["kind"] == "reel":
            render_reel(p, out)
        else:
            render_carousel(p, out)
        print(f"{p['id']}: {p['kind']}, {len(p['rows'])} frames -> {out.relative_to(HERE)}")
    hl = ig / "highlights"
    hl.mkdir(parents=True, exist_ok=True)
    for s in parse_stories(md):
        render_story(s, hl)
    for n, g in enumerate(["1·2·3", "12", "₸", "[ ]", "§"], 1):
        render_highlight_cover(n, g, hl)
    print("highlights: stories and covers ->", hl.relative_to(HERE))
    render_brand(HERE)
    print("brand: avatar and covers ->", HERE.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
