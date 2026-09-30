"""The wordmark in Inter SemiBold (the site's typeface), letters as outlines: SVG in black, blue and white.
    python3 make_logo.py "Konsilier AI" konsilier-logo-plain"""
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

text, stem = sys.argv[1], sys.argv[2]
f = instantiateVariableFont(TTFont("../stamp/fonts/inter-latin.woff2"), {"wght": 600})
gs, cmap, upm, hmtx = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm, f["hmtx"]
track = -0.03 * upm  # the site sets the logo with tracking -0.03em
x, paths, top, bottom = 0.0, [], 0.0, 0.0
for ch in text:
    g = cmap[ord(ch)]
    pen = SVGPathPen(gs); gs[g].draw(pen)
    if pen.getCommands():
        paths.append(f'<path transform="translate({x:.1f} 0)" d="{pen.getCommands()}"/>')
    b = BoundsPen(gs); gs[g].draw(b)
    if b.bounds: bottom, top = min(bottom, b.bounds[1]), max(top, b.bounds[3])
    x += hmtx[g][0] + track
width, pad = x - track, 0.02 * upm
vb = f"{-pad:.0f} {-(top + pad):.0f} {width + 2 * pad:.0f} {top - bottom + 2 * pad:.0f}"
for name, fill in (("black", "#0d0d0d"), ("blue", "#0084ff"), ("white", "#ffffff")):
    open(f"{stem}-{name}.svg", "w").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"><g fill="{fill}" transform="scale(1,-1)">{"".join(paths)}</g></svg>\n')
