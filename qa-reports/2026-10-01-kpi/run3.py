from sim import *
import sys
SC=[("Возврат за товар","Купил холодильник за 380000 тенге в магазине «Мечта» в Астане 05.09.2026, не морозит, магазин отказывается вернуть деньги. Чек есть."),
    ("Невыплата зарплаты","Работодатель ТОО «Строй-Альфа» не выплатил зарплату за 3 месяца, 900 000 тенге. Я уволился 01.09.2026, трудовой договор есть."),
    ("Жалоба на госорган","Акимат района уже 2 месяца не отвечает на моё заявление о ремонте дороги, подал 01.08.2026 через eOtinish. Хочу пожаловаться.")]
out=[]
for name,text in SC:
    T0=time.time(); clicks=0; ev=[]; rec={"scenario":name}
    def mark(step,**kw): ev.append({"t":round(time.time()-T0,1),"step":step,**kw})
    try:
        st,u,dt=call("POST","/users",json={"language":"ru","country":"KZ","src":"qa-test"}); tok=u["token"]
        clicks+=1  # отправить вопрос
        st,c,dt=call("POST","/cases",tok,json={"text":"QA-TEST. "+text,"language":"ru","country":"KZ","accept_terms":"2026-09-29","defer":True}); cid=c["case"]["id"]; mark("case",st=st,dt=dt)
        r=chat(tok,cid,"QA-TEST. "+text); mark("chat",ttft=r.get("ttft"),total=r.get("total"),chars=len(r.get("text","")),offer="[[DOCUMENT]]" in (r.get("text") or ""))
        rec["chat_short"]=(r.get("text") or "")[:300]
        clicks+=1  # «Составить документ» → страница дела
        time.sleep(1)
        cs=None
        for i in range(12):
            st,cs,dt=call("GET",f"/cases/{cid}",tok)
            if cs.get("scenario") or cs.get("status")!="intake": break
            time.sleep(2)
        mark("case_open",status=cs.get("status"),scenario=(cs.get("scenario") or {}).get("id"),q=(cs.get("question") or {}).get("field"),prop=(cs.get("proposal") or {}).get("type"))
        # ответы на вопросы, если остались
        qs=0
        while cs.get("status")=="intake" and cs.get("question") and qs<10:
            q=cs["question"]; a="Пропустить" if q.get("type")=="evidence" or q.get("optional") else ("20.09.2026" if q.get("type")=="date" else "Акимат Алмалинского района г. Алматы" if "name" in q.get("field","") or "respondent" in q.get("field","") else "г. Алматы, ул. Абая, 1" if "address" in q.get("field","") else "Подробности см. выше")
            st,r2,dt=call("POST",f"/cases/{cid}/messages",tok,json={"text":a}); clicks+=1; qs+=1
            mark("answer",field=q.get("field"),type=q.get("type"),a=a,st=st,dt=dt,reply=((r2.get("reply") or {}).get("message") or "")[:120] if isinstance(r2,dict) else r2)
            cs=r2.get("case",cs) if isinstance(r2,dict) else cs
            if st>=400: break
        st,dr,dt=call("GET",f"/cases/{cid}/draft",tok)
        mark("draft",st=st,dt=dt,visible=len(dr.get("visible","")) if isinstance(dr,dict) else 0,blanks=[b.get("field") if isinstance(b,dict) else b for b in (dr.get("blanks") or [])] if isinstance(dr,dict) else None,keys=list(dr.keys()) if isinstance(dr,dict) else dr)
        rec["draft_head"]=(dr.get("visible","") if isinstance(dr,dict) else "")[:600]
        rec["t_draft"]=round(time.time()-T0,1); rec["clicks_draft"]=clicks
        clicks+=1  # «Подготовить документ»
        st,nx,dt=call("POST",f"/cases/{cid}/actions/next",tok,json={})
        pay=(nx.get("payment") if isinstance(nx,dict) else None); cv=nx.get("case",{}) if isinstance(nx,dict) else {}
        mark("actions_next",st=st,dt=dt,payment=bool(pay),err=None if st<400 else nx)
        p=cv.get("payment") or {}
        if not p.get("invoice_id"):
            st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":"document"}); clicks+=1
            mark("payment",st=st,dt=dt,err=None if st<400 else pp); p=(pp.get("case",{}) if isinstance(pp,dict) else {}).get("payment") or {}
        rec["invoice"]={k:p.get(k) for k in ("amount","currency","status","code","method")} ; rec["t_invoice"]=round(time.time()-T0,1); rec["clicks_invoice"]=clicks
        rec["case_id"]=cid
    except Exception as e: rec["exc"]=repr(e)[:300]
    rec["events"]=ev; out.append(rec)
    print(json.dumps({k:rec.get(k) for k in ("scenario","t_draft","clicks_draft","t_invoice","clicks_invoice","invoice","exc")},ensure_ascii=False),flush=True)
    for e in ev: print("   ",json.dumps(e,ensure_ascii=False)[:260])
json.dump(out,open(sys.argv[1] if len(sys.argv)>1 else "run3.json","w"),ensure_ascii=False,indent=1)
