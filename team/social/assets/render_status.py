"""Render WhatsApp status / story cards for the launch 02.10.2026 (team/launch/2026-10-02-launch.md §2.3, §3).

Outputs team/social/assets/launch/status/{s1,s2,ref}-{ru,kk}.png, 1080x1920, white background, brand K mark.
Usage: pip install pillow && python team/social/assets/render_status.py
Styling, font and K mark come from render.py.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import render as r

OUT = Path(__file__).resolve().parent / "launch" / "status"
BRAND = {
    "ru": "ИИ-помощник по правовым вопросам",
    "kk": "Заң мәселелері бойынша ЖИ-көмекші",
}

CARDS = {
    "s1-ru": ("Не возвращают деньги, зарплату или залог?",
              ["Опишите ситуацию — ИИ бесплатно разберёт её.", "Претензию подготовит за несколько минут."],
              "Документ — 1 990 ₸"),
    "s1-kk": ("Ақшаңызды, жалақыңызды не кепіліңізді қайтармай жүр ме?",
              ["Жағдайды жазыңыз — ЖИ оны тегін талдайды.", "Кінәрат-талапты бірнеше минутта дайындайды."],
              "Құжат — 1 990 ₸"),
    "s2-ru": ("Сегодня запустили Konsiliér AI",
              ["Опишите проблему словами или голосом.", "Получите претензию, жалобу или заявление.",
               "Подаёте сами, онлайн."],
              "Документ — 1 990 ₸"),
    "s2-kk": ("Бүгін Konsiliér AI іске қосылды",
              ["Мәселені жазыңыз не айтып беріңіз.", "Кінәрат-талап, шағым не арыз алыңыз.",
               "Өзіңіз онлайн бересіз."],
              "Құжат — 1 990 ₸"),
    "ref-ru": ("Оплатили документ? Отправьте ссылку другу",
               ["После его первой оплаты вы оба получите ещё один документ бесплатно.",
                "Ваша ссылка — в профиле и на готовом документе."],
               "konsilier.com"),
    "ref-kk": ("Құжатқа төледіңіз бе? Досыңызға сілтеме жіберіңіз",
               ["Ол алғаш төлегеннен кейін екеуіңіз де тағы бір құжатты тегін аласыз.",
                "Сілтемеңіз — профильде және дайын құжатта."],
               "konsilier.com"),
}


def card(lang: str, title: str, lines: list[str], tag: str) -> Image.Image:
    im = Image.new("RGB", (r.RW, r.RH), r.WHITE)
    d = ImageDraw.Draw(im)
    side, width = r.SIDE, r.RW - 2 * r.SIDE
    r.header(d, r.RW, False, None, top=r.SAFE_TOP - 120)
    for tsize in (84, 78, 72, 66, 60):
        tf = r.font(tsize, 700)
        if r.block_height(title, tf, width, 1.1) <= 4 * tsize * 1.1:
            break
    y = r.SAFE_TOP + 60
    y = r.text_block(d, side, y, title, tf, r.INK, width, 1.1) + 36
    r.accent_bar(d, side, y)
    y += 80
    bf = r.font(44, 500)
    for line in lines:
        y = r.text_block(d, side, y, line, bf, r.INK, width) + 28
    y += 30
    tf2 = r.font(52, 700)
    d.text((side, y), tag, font=tf2, fill=r.NAVY)
    f = r.font(34, 600)
    d.text((side, r.SAFE_BOTTOM + 20), "konsilier.com", font=f, fill=r.NAVY)
    d.text((side, r.SAFE_BOTTOM + 70), BRAND[lang], font=r.font(28, 500), fill=r.MUTED)
    return im


def main() -> int:
    r.ensure_font()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (title, lines, tag) in CARDS.items():
        card(name.rsplit("-", 1)[1], title, lines, tag).save(OUT / f"{name}.png", optimize=True)
        print(OUT / f"{name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
