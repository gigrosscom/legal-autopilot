"""Round stamp Ø40 mm after sample №35: rope edge, Kazakh outer ring, Russian inner ring, BIN at the bottom,
the name in the centre. Output: SVG (mm units), rendered to PDF/PNG with Chromium."""
import base64, math, pathlib, sys

FONTS = pathlib.Path(__file__).parent / "fonts"
# Inter, the site's typeface (latin, cyrillic and cyrillic-ext for Қ Ә Ң Ө Ұ Ү Һ Ғ), embedded so the file is self-contained
RANGES = {"inter-latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
          "inter-cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
          "inter-cyrillic-ext": "U+0460-052F,U+1C80-1C88,U+20B4,U+2DE0-2DFF,U+A640-A69F,U+FE2E-FE2F"}

def font_css():
    out = []
    for name, rng in RANGES.items():
        b64 = base64.b64encode((FONTS / f"{name}.woff2").read_bytes()).decode()
        out.append(f"@font-face{{font-family:'Inter Stamp';src:url(data:font/woff2;base64,{b64}) format('woff2');font-weight:100 900;unicode-range:{rng}}}")
    return "".join(out)


def arc(r, a0, a1, sweep):
    c = 20.0
    x0, y0 = c + r*math.cos(math.radians(a0)), c + r*math.sin(math.radians(a0))
    x1, y1 = c + r*math.cos(math.radians(a1)), c + r*math.sin(math.radians(a1))
    span = (a1 - a0) % 360 if sweep else (a0 - a1) % 360
    large = 1 if span > 180 else 0
    return f"M {x0:.3f} {y0:.3f} A {r} {r} 0 {large} {sweep} {x1:.3f} {y1:.3f}"

def stamp(name, center, ink="#000"):
    c = 20.0
    teeth = []
    n = 96
    for i in range(2*n + 1):
        a = math.radians(i * 360 / (2*n))
        r = 19.72 if i % 2 == 0 else 18.98
        teeth.append(f"{c + r*math.cos(a):.3f},{c + r*math.sin(a):.3f}")
    outer_txt = f"ҚАЗАҚСТАН РЕСПУБЛИКАСЫ АЛМАТЫ ҚАЛАСЫ «{name}» ЖАУАПКЕРШІЛІГІ ШЕКТЕУЛІ СЕРІКТЕСТІГІ ★"
    inner_txt = "РЕСПУБЛИКА КАЗАХСТАН Г. АЛМАТЫ ТОВАРИЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ"
    bin_txt = "★ БСН 260940036818 БИН ★"
    r_out, r_in, r_bin = 16.45, 13.45, 15.02
    full_out = 2*math.pi*r_out
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm" viewBox="0 0 40 40">
  <defs>
    <style>{font_css()}</style>
    <path id="outer" d="M {c} {c + r_out} A {r_out} {r_out} 0 1 1 {c} {c - r_out} A {r_out} {r_out} 0 1 1 {c} {c + r_out}"/>
    <path id="inner" d="{arc(r_in, 141, 39, 1)}"/>
    <path id="bin" d="{arc(r_bin, 148, 32, 0)}"/>
  </defs>
  <g fill="none" stroke="{ink}" stroke-linejoin="round">
    <circle cx="{c}" cy="{c}" r="19.86" stroke-width="0.26"/>
    <polyline points="{' '.join(teeth)}" stroke-width="0.2"/>
    <circle cx="{c}" cy="{c}" r="18.72" stroke-width="0.26"/>
    <circle cx="{c}" cy="{c}" r="15.72" stroke-width="0.22"/>
    <circle cx="{c}" cy="{c}" r="12.55" stroke-width="0.32"/>
  </g>
  <g fill="{ink}" font-family="Inter Stamp, Inter, Arial, sans-serif" font-weight="750">
    <text font-size="1.9"><textPath href="#outer" startOffset="0" textLength="{full_out*0.985:.2f}" lengthAdjust="spacingAndGlyphs">{outer_txt}</textPath></text>
    <text font-size="1.52"><textPath href="#inner" startOffset="50%" text-anchor="middle" textLength="{2*math.pi*r_in*256/360:.2f}" lengthAdjust="spacingAndGlyphs">{inner_txt}</textPath></text>
    <text font-size="1.4" letter-spacing="0.02"><textPath href="#bin" startOffset="50%" text-anchor="middle">{bin_txt}</textPath></text>
    <text x="{c}" y="{c + 1.35}" font-size="4.1" font-weight="650" letter-spacing="-0.12" text-anchor="middle">{center}</text>
  </g>
</svg>'''

if __name__ == "__main__":
    out = sys.argv[1]
    # centre: the name as the site's logo sets it (mixed case, semibold, tight); the rings keep capitals
    for key, name, center in (("main", "KONSILIER AI", "Konsilier AI"), ("accent", "KONSILIÉR AI", "Konsiliér AI")):
        for tone, ink in (("black", "#000"), ("blue", "#1f3fbf")):
            open(f"{out}/stamp-{key}-{tone}.svg", "w").write(stamp(name, center, ink))
