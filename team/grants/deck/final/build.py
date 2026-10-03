import sys
CSS='''@font-face{font-family:Inter;src:url('fonts/Inter.ttf') format('truetype');font-weight:100 900}
:root{--blue:#0866ff;--blue2:#0064e0;--ink:#0d0d0d;--sec:#4f4f55;--muted:#6e6e73;--soft:#f0f0f2;--line:#e4e6eb;--navy:#0b172a}
@page{size:1280px 720px;margin:0}*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.s{width:1280px;height:720px;position:relative;overflow:hidden;padding:60px 76px 70px;background:#fff;break-after:page;display:flex;flex-direction:column}
.s:last-child{break-after:auto}
.ey{font-size:14px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--blue)}
h1{font-size:44px;line-height:1.1;font-weight:700;letter-spacing:-.03em;margin-top:12px;max-width:1080px}
.lead{font-size:19px;line-height:1.5;color:var(--sec);margin-top:14px;max-width:960px}
.g{display:grid;gap:18px;margin-top:34px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}
.c{background:var(--soft);border-radius:18px;padding:24px}
.c h3{font-size:19px;font-weight:700;letter-spacing:-.01em;margin-bottom:8px}.c p{font-size:15px;line-height:1.5;color:var(--sec)}
.n{width:34px;height:34px;border-radius:9px;background:var(--blue);color:#fff;font-weight:700;font-size:16px;display:flex;align-items:center;justify-content:center;margin-bottom:16px}
.big{font-size:52px;font-weight:700;letter-spacing:-.03em;color:var(--blue);line-height:1}
.lbl{font-size:15px;line-height:1.4;color:var(--ink);margin-top:10px;font-weight:500}
.src{font-size:11.5px;color:var(--muted);margin-top:8px;line-height:1.35}
.note{margin-top:auto;font-size:17px;font-weight:600;color:var(--blue)}
.foot{position:absolute;left:76px;right:76px;bottom:24px;display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.logo{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:-.03em;font-size:18px}.logo i{width:22px;height:22px;border-radius:6px;background:var(--blue);display:block}
table{width:100%;border-collapse:collapse;margin-top:26px;font-size:15px}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}td.us,th.us{background:#eef4ff;color:var(--blue2);font-weight:700}
.cover{background:linear-gradient(120deg,#0b1220 0%,#0b1d45 60%,#0a3a9e 100%);color:#fff;justify-content:space-between}
.cover .ey{color:#5aa9ff}.cover h1{font-size:68px;color:#fff;max-width:1000px}.cover .lead{color:#c9d3e6;font-size:22px}
.top{display:flex;justify-content:space-between;align-items:center;font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#9fb0cc;font-weight:600}
.row{display:flex;justify-content:space-between;font-size:15px;color:#9fb0cc}
.kv{display:grid;grid-template-columns:1fr auto;gap:10px 24px;font-size:16px;margin-top:6px}.kv b{color:var(--blue2)}
.ph{display:grid;grid-template-columns:150px 1fr 1fr;gap:0}.ph div{padding:12px 10px;border-bottom:1px solid var(--line);font-size:15px;line-height:1.4}.ph .h{font-weight:700;color:var(--blue2)}
.pill{display:inline-block;background:#eef4ff;color:var(--blue2);border-radius:999px;padding:4px 12px;font-size:13px;font-weight:600;margin:6px 6px 0 0}
'''
def build(T,lang,out):
    N=len(T['slides'])+1
    h=[f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>Konsilier — {T["title"]}</title><style>{CSS}</style></head><body>']
    c=T['cover']
    h.append(f'<section class="s cover"><div class="top"><span class="logo" style="color:#fff;font-size:20px;letter-spacing:-.03em;text-transform:none"><i></i>Konsilier</span><span>{c["tag"]}</span></div><div><div class="ey">{c["ey"]}</div><h1>{c["h"]}</h1><p class="lead">{c["sub"]}</p></div><div class="row"><span>{c["l"]}</span><span>{c["r"]}</span></div></section>')
    for i,(ey,ttl,body) in enumerate(T['slides'],2):
        h.append(f'<section class="s"><div class="ey">{ey}</div><h1>{ttl}</h1>{body}<div class="foot"><span class="logo" style="font-size:13px"><i style="width:14px;height:14px;border-radius:4px"></i>Konsilier · {T["foot"]}</span><span>{i} / {N}</span></div></section>')
    h.append('</body></html>')
    open(out,'w').write(''.join(h))
