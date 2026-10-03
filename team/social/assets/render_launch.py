"""Render launch assets for team/content/launch-12.md (Konsiliér AI, launch 02.10.2026).

Outputs (relative to team/social/assets/launch/):
  l-01 … l-05/cover.png   video covers, 1080x1920
  l-06 … l-09/NN.png      carousel slides, 1080x1440
  l-10 … l-12/NN.png      story backgrounds, 1080x1920, lower zone left empty for the in-app sticker

Usage: pip install pillow && python team/social/assets/render_launch.py
Texts come from the "| № | Фон | …" tables in launch-12.md; styling, font and K mark from render.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import render as r

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / "content" / "launch-12.md"
OUT = HERE / "launch"

_footer = r.footer


def footer(d, w, h, dark, side=96, text="konsilier.com"):
    # decision 30.09.2026: "ИИ-помощник по правовым вопросам" everywhere (render.py still has the older wording)
    _footer(d, w, h, dark, side, text.replace("по юридическим вопросам", "по правовым вопросам"))


r.footer = footer

STICKER_TOP, STICKER_BOTTOM = 1100, 1560  # empty zone for poll / quiz / link / question sticker


def parse(md: str) -> list[dict]:
    posts = []
    parts = re.split(r"^### (L-\d\d) — (\S+)", md, flags=re.M)
    for i in range(1, len(parts), 3):
        pid, kind, body = parts[i], parts[i + 1], parts[i + 2]
        rows = []
        lines = body.splitlines()
        for j, line in enumerate(lines):
            if line.startswith("| №") and "Фон" in line:
                cols = r.split_row(line)
                k = j + 2
                while k < len(lines) and lines[k].startswith("|"):
                    cells = [c.replace("Konsiliér AI", "Konsiliér\u00a0AI") for c in r.split_row(lines[k])]
                    rows.append(dict(zip(cols, cells)))
                    k += 1
                break
        posts.append({"id": pid, "kind": kind, "rows": rows})
    return posts


def clean(cell: str) -> str:
    return "" if cell.strip() in ("—", "-") else cell


def story_frame(row: dict) -> Image.Image:
    dark = row["Фон"].startswith("тём")
    im = Image.new("RGB", (r.RW, r.RH), r.NAVY if dark else r.WHITE)
    d = ImageDraw.Draw(im)
    side, width = r.SIDE, r.RW - 2 * r.SIDE
    r.header(d, r.RW, dark, None, top=r.SAFE_TOP - 120)
    title_c = r.WHITE if dark else r.NAVY
    sub_c = r.ACCENT if dark else r.MUTED
    body_c = r.WHITE if dark else r.INK
    ru_t, kk_t = clean(row["Заголовок ru"]), clean(row["Заголовок kk"])
    ru_items = r.items(clean(row["Текст ru"]))
    kk_items = r.items(clean(row["Текст kk"]))
    for tsize in (72, 66, 60, 54, 48):
        tf, kf = r.font(tsize, 700), r.font(int(tsize * 0.56), 500)
        f_ru, f_kk = r.font(int(tsize * 0.6), 600), r.font(int(tsize * 0.46), 450)
        need = r.block_height(ru_t, tf, width, 1.1) + (r.block_height(kk_t, kf, width) + 8 if kk_t else 0) + 96
        need += sum(r.block_height(t, f_ru, width) + 30 for t in ru_items)
        need += sum(r.block_height(t, f_kk, width) + 30 for t in kk_items)
        if r.SAFE_TOP + 40 + need < STICKER_TOP - 20:
            break
    y = r.SAFE_TOP + 40
    y = r.text_block(d, side, y, ru_t, tf, title_c, width, 1.1)
    if kk_t:
        y = r.text_block(d, side, y + 8, kk_t, kf, sub_c, width)
    y += 26
    r.accent_bar(d, side, y)
    y += 70
    if kk_items and len(kk_items) == len(ru_items):
        for a, b in zip(ru_items, kk_items):
            y = r.text_block(d, side, y, a, f_ru, body_c, width)
            y = r.text_block(d, side, y + 4, b, f_kk, sub_c, width) + 30
    else:
        for a in ru_items:
            y = r.text_block(d, side, y, a, f_ru, body_c, width) + 30
    f = r.font(30, 500)
    d.text((side, r.SAFE_BOTTOM + 60), "konsilier.com", font=f, fill=sub_c)
    return im


def main() -> int:
    r.ensure_font()
    posts = parse(SOURCE.read_text(encoding="utf-8"))
    for p in posts:
        out = OUT / p["id"].lower()
        out.mkdir(parents=True, exist_ok=True)
        if not p["rows"]:
            print(f"{p['id']}: no table", file=sys.stderr)
            continue
        if p["kind"] == "видео":
            r.reel_frame(p["rows"][0], True).save(out / "cover.png", optimize=True)
            n = 1
        elif p["kind"] == "карусель":
            r.render_carousel(p, out)
            n = len(p["rows"])
        else:
            for i, row in enumerate(p["rows"], 1):
                story_frame(row).save(out / f"{i:02d}.png", optimize=True)
            n = len(p["rows"])
        print(f"{p['id']}: {p['kind']}, {n} file(s) -> {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
