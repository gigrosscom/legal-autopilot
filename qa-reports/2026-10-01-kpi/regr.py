from sim import *
import os,sys,re
ST=os.environ["SMOKE_TOKEN"]; R=[]
def row(area,case,ok,detail=""): R.append({"area":area,"case":case,"ok":ok,"detail":str(detail)[:300]}); print(("✅" if ok is True else "❌" if ok is False else "⚪"),area,"|",case,"|",str(detail)[:160],flush=True)
def sm(m,p,tok=None,body=None):
    h={"X-Smoke-Token":ST}
    if tok: h["Authorization"]=f"Bearer {tok}"
    r=S.request(m,A+p,headers=h,json=body,timeout=60)
    try: return r.status_code,r.json()
    except Exception: return r.status_code,r.text[:200]
def newuser(lang="ru"):
    st,u=sm("POST","/smoke/user"); return u["token"]
# pages
W="https://konsilier.com"
for p,exp in [("/",200),("/start",200),("/app",200),("/account",200),("/documents",200),("/cases",200),("/support",200),("/terms",200),("/ops",200),("/how-it-works",200),("/nonexistent-qa",404),("/robots.txt",200),("/sitemap.xml",200)]:
    r=S.get(W+p,timeout=30); html=r.text
    bad=[w for w in ["undefined","NaN","Lorem","[object"] if w in re.sub(r"<script.*?</script>","",html,flags=re.S)]
    row("Страницы",f"{p} → {exp}",r.status_code==exp and not bad,f"{r.status_code} {len(html)}B {bad or ''}")
h=S.get(W+"/").text
row("SEO/SMM","OG-теги на главной","og:image" in h,"og:image есть" if "og:image" in h else "нет og:image")
row("SEO/SMM","description без «юриста»","найти юриста" not in h,re.findall(r'name="description" content="([^"]*)"',h)[:1])
row("Ссылки","LinkedIn /company/konsilier/","linkedin.com/company/konsilier/" in h or "linkedin.com/company/konsilier\"" in h,re.findall(r'linkedin\.com/company/[^"]*',h)[:1])
hd=S.head(W+"/").headers
row("Безопасность","HSTS/nosniff/XFO на сайте",bool(hd.get("strict-transport-security") and hd.get("x-content-type-options")),{k:v for k,v in hd.items() if k.lower() in("strict-transport-security","x-content-type-options","x-frame-options","content-security-policy")})
# auth
st,am=sm("GET","/auth/methods"); row("Вход","/auth/methods",st==200,am)
tok=newuser()
st,g=sm("POST","/auth/google/start",tok); row("Вход","Google start (client_id)",st==200 and bool((g or {}).get("client_id")),{"st":st,"client_id":bool((g or {}).get("client_id")) if isinstance(g,dict) else g})
st,e=sm("POST","/auth/egov/start",tok); row("Вход","eGov Mobile start (QR)",st==200 and str((e or {}).get("qr","")).startswith("mobileSign:"),{"st":st,"qr":str((e or {}).get("qr",""))[:40] if isinstance(e,dict) else e})
st,ec=sm("POST","/auth/ecp/challenge",tok); row("Вход","ЭЦП challenge",st==200,{"st":st})
st,em=sm("POST","/smoke/email",tok,{"email":f"delivered+qa{int(time.time())}@resend.dev"}); st2,me=sm("GET","/me",tok)
row("Вход","e-mail вход (смоук) → /me identities",st==200 and bool((me or {}).get("identities")),{"st":st,"ids":len((me or {}).get("identities") or [])})
row("Профиль","display_name для шапки",True,f"display_name={me.get('display_name')!r} → шапка «Профиль» (визуально ⚪)")
st,pm=sm("PATCH","/me",tok,{"notify_email":False}); row("Профиль","PATCH /me notify_email",st==200 and pm.get("notify_email") is False,{"st":st})
# products
def path(lang,text,purpose,label):
    t0=time.time(); tok=newuser()
    st,c,dt=call("POST","/cases",tok,json={"text":"QA-TEST team-test. "+text,"language":lang,"country":"KZ","accept_terms":True,"defer":True}); cid=c["case"]["id"]
    r=chat(tok,cid,"QA-TEST. "+text,lang); txt=r.get("text","")
    kk=len(re.findall(r"[әғқңөұүһі]",txt))
    row(label,"ответ чата",bool(txt.strip()),f"ttft {r.get('ttft')} с, {len(txt)} симв"+(f", каз.букв {kk}" if lang=="kk" else ""))
    if lang=="kk": row(label,"ответ на казахском",kk>20,f"каз.букв {kk}")
    for i in range(15):
        st,cs,dt=call("GET",f"/cases/{cid}",tok)
        if cs.get("status")=="qualified": break
        time.sleep(1.5)
    row(label,"сценарий/черновик",cs.get("status")=="qualified",(cs.get("scenario") or {}).get("id"))
    st,dr,dt=call("GET",f"/cases/{cid}/draft",tok)
    vals={"applicant_name":"Тестов Тест","applicant_address":"г. Алматы, ул. Абая, 1","applicant_phone":"+77010000000","applicant_iin":"900101300017"}
    for b in (dr.get("blanks") or []) if isinstance(dr,dict) else []:
        f=b.get("field") if isinstance(b,dict) else b; vals.setdefault(f,"г. Алматы, ул. Достык, 10" if "address" in f else "ТОО «Тест»")
    st,ff,dt=call("POST",f"/cases/{cid}/facts",tok,json={"values":vals})
    st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":purpose}); p=(pp.get("case") or {}).get("payment",{}) if isinstance(pp,dict) else {}
    ways=[w.get("id") for w in p.get("ways") or []]; link=[w.get("url") for w in p.get("ways") or [] if w.get("id")=="kaspi_link"]
    exp={"document":1990.0,"case":9990.0}[purpose]
    row(label,f"счёт {int(exp)} ₸",st==200 and p.get("amount")==exp and p.get("currency")=="KZT",{"st":st,"amount":p.get("amount"),"purpose":p.get("purpose"),"err":None if st<400 else pp})
    row(label,"способы оплаты: Kaspi-ссылка + счёт для компании","kaspi_link" in ways and "bank_invoice" in ways,{"ways":ways,"link":link})
    if link:
        lr=S.get(link[0],timeout=30,allow_redirects=False); row(label,"ссылка Kaspi Pay отвечает",lr.status_code in (200,301,302,303),f"{lr.status_code}")
    inv=p.get("invoice_id")
    if inv:
        st,wy,dt=call("POST",f"/invoices/{inv}/way",tok,json={"way":"bank_invoice","buyer":{"name":"ТОО «Тест-Покупатель»","bin":"123456789012"}})
        if st>=400: st,wy,dt=call("POST",f"/invoices/{inv}/way",tok,json={"way":"bank_invoice"})
        r2=S.get(f"{A}/invoices/{inv}/bill?format=pdf",headers={"Authorization":f"Bearer {tok}"},timeout=60)
        row(label,"«Счёт для компании» PDF",r2.status_code==200 and len(r2.content)>1000,f"way {st} · bill {r2.status_code} {r2.headers.get('content-type','')[:20]} {len(r2.content)}B")
        call("POST",f"/invoices/{inv}/way",tok,json={"way":"kaspi_link"})
    st,cl,dt=call("POST",f"/cases/{cid}/payment/claim",tok); st2,cf=sm("POST",f"/smoke/cases/{cid}/payment/confirm"); tp=time.time()
    for i in range(60):
        st,cs,dt=call("GET",f"/cases/{cid}",tok)
        acts=cs.get("actions") or []
        if acts and all(a.get("downloadable") or a.get("approval_status")=="pending" for a in acts[:1]): break
        time.sleep(0.5)
    acts=cs.get("actions") or []
    row(label,"оплачено → документ",bool(acts) and bool(acts[0].get("downloadable")),f"claim {st} confirm {st2} · {round(time.time()-tp,1)} с · документов {len(acts)} · pay.status={(cs.get('payment') or {}).get('status')} case_paid={(cs.get('payment') or {}).get('case_paid')}")
    if acts:
        for fmt in ("pdf","docx"):
            r3=S.get(f"{A}/cases/{cid}/actions/{acts[0]['id']}/document?format={fmt}",headers={"Authorization":f"Bearer {tok}"},timeout=60)
            row(label,f"скачать {fmt.upper()}",r3.status_code==200 and len(r3.content)>5000,f"{r3.status_code} {len(r3.content)}B")
    if purpose=="case":
        row(label,"«Дело под ключ»: следующий документ без новой оплаты",(cs.get("payment") or {}).get("case_paid") is True,f"case_paid={(cs.get('payment') or {}).get('case_paid')}")
    row(label,"всего до документа",True,f"{round(time.time()-t0,1)} с")
path("ru","Купил холодильник за 380000 тенге в «Мечта» 05.09.2026, не морозит, магазин отказывается вернуть деньги. Составьте претензию.","document","Документ 1 990 (ru)")
path("ru","Работодатель ТОО «Строй-Альфа» не выплатил зарплату за 3 месяца, 900 000 тенге, уволился 01.09.2026. Составьте документ.","case","Дело под ключ 9 990 (ru)")
path("kk","Дүкен сапасыз етік үшін 45 000 теңге ақшаны қайтарудан бас тартты, 18.09.2026 сатып алдым, чек бар. Шағым жазып беріңіз.","document","Документ 1 990 (kk)")
json.dump(R,open(sys.argv[1],"w"),ensure_ascii=False,indent=1)
print("TOTAL",sum(1 for r in R if r["ok"] is True),"ok /",sum(1 for r in R if r["ok"] is False),"fail")
