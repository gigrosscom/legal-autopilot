"""Round stamp Ø40 mm after sample №35: rope edge, Kazakh outer ring, Russian inner ring, BIN at the bottom,
the name in the centre. Output: SVG (mm units), rendered to PDF/PNG with Chromium."""
import math, sys

def arc(r, a0, a1, sweep):
    c = 20.0
    x0, y0 = c + r*math.cos(math.radians(a0)), c + r*math.sin(math.radians(a0))
    x1, y1 = c + r*math.cos(math.radians(a1)), c + r*math.sin(math.radians(a1))
    span = (a1 - a0) % 360 if sweep else (a0 - a1) % 360
    large = 1 if span > 180 else 0
    return f"M {x0:.3f} {y0:.3f} A {r} {r} 0 {large} {sweep} {x1:.3f} {y1:.3f}"

def stamp(name, ink="#000"):
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
  <g fill="{ink}" font-family="DejaVu Sans, Arial, sans-serif" font-weight="700">
    <text font-size="1.9"><textPath href="#outer" startOffset="0" textLength="{full_out*0.985:.2f}" lengthAdjust="spacingAndGlyphs">{outer_txt}</textPath></text>
    <text font-size="1.52"><textPath href="#inner" startOffset="50%" text-anchor="middle" textLength="{2*math.pi*r_in*256/360:.2f}" lengthAdjust="spacingAndGlyphs">{inner_txt}</textPath></text>
    <text font-size="1.4" letter-spacing="0.02"><textPath href="#bin" startOffset="50%" text-anchor="middle">{bin_txt}</textPath></text>
    <text x="{c}" y="{c + 1.15}" font-size="3.25" text-anchor="middle" textLength="20.4" lengthAdjust="spacingAndGlyphs">«{name}»</text>
  </g>
</svg>'''

if __name__ == "__main__":
    out = sys.argv[1]
    for key, name in (("main", "KONSILIER AI"), ("accent", "KONSILIÉR AI")):
        for tone, ink in (("black", "#000"), ("blue", "#1f3fbf")):
            open(f"{out}/stamp-{key}-{tone}.svg", "w").write(stamp(name, ink))
