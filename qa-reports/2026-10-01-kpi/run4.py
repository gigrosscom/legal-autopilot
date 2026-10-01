from sim import *
import os,sys
ST=os.environ["SMOKE_TOKEN"]
def smoke(m,p):
    r=S.request(m,A+p,headers={"X-Smoke-Token":ST},timeout=60)
    try: return r.status_code,r.json()
    except Exception: return r.status_code,r.text[:200]
SC=[("Возврат за товар","Купил холодильник за 380000 тенге в магазине «Мечта» в Астане 05.09.2026, не морозит, магазин отказывается вернуть деньги. Чек есть. Составьте претензию."),
    ("Невыплата зарплаты","Работодатель ТОО «Строй-Альфа» не выплатил зарплату за 3 месяца, 900 000 тенге. Я уволился 01.09.2026, трудовой договор есть. Составьте документ."),
    ("Жалоба на госорган","Акимат района уже 2 месяца не отвечает на моё заявление о ремонте дороги, подал 01.08.2026 через eOtinish. Составьте жалобу.")]
out=[]
for name,text in SC:
    rec={"scenario":name}; T0=time.time(); taps=0
    def t(): return round(time.time()-T0,1)
    try:
        st,u=smoke("POST","/smoke/user"); 
        if st!=200: raise SystemExit(f"smoke/user {st} {u}")
        tok=u["token"]
        st,c,dt=call("POST","/cases",tok,json={"text":"QA-TEST. "+text,"language":"ru","country":"KZ","accept_terms":True,"defer":True}); cid=c["case"]["id"]; taps+=1
        r=chat(tok,cid,"QA-TEST. "+text); rec["ttft"]=r.get("ttft"); rec["offer"]="[[DOCUMENT]]" in (r.get("text") or "")
        taps+=1  # Составить документ
        for i in range(20):
            st,cs,dt=call("GET",f"/cases/{cid}",tok)
            if cs.get("status")!="intake" or cs.get("scenario"): break
            time.sleep(1.5)
        rec["scenario_id"]=(cs.get("scenario") or {}).get("id"); rec["status"]=cs.get("status")
        st,dr,dt=call("GET",f"/cases/{cid}/draft",tok); rec["t_draft"]=t() if st==200 else None
        if cs.get("status")!="qualified": raise SystemExit(f"тупик: status={cs.get('status')} draft={st}")
        st,nx,dt=call("POST",f"/cases/{cid}/actions/next",tok,json={}); taps+=1
        p=(nx.get("case") or {}).get("payment") or {}
        if not p.get("invoice_id"):
            st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":"document"})
            if st==422 and isinstance(pp,dict) and (pp.get("detail") or {}).get("code")=="applicant_data_required":
                vals={"applicant_name":"Тестов Тест Тестович","applicant_address":"г. Алматы, ул. Абая, 1, кв. 1","applicant_phone":"+77010000000"}
                for b in (dr.get("blanks") or []) if isinstance(dr,dict) else []:
                    f=b.get("field") if isinstance(b,dict) else b
                    vals.setdefault(f,"900101300017" if "iin" in f else "г. Алматы, ул. Достык, 10" if "address" in f else "Тест")
                st,ff,dt=call("POST",f"/cases/{cid}/facts",tok,json={"values":vals}); taps+=1; rec["facts"]=[st, None if st<400 else ff]
                st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":"document"})
            if st>=400: raise SystemExit(f"payment {st} {pp}")
            p=pp["case"]["payment"]
        rec["t_invoice"]=t(); rec["invoice"]={k:p.get(k) for k in ("amount","currency","code","status")}
        st,cl,dt=call("POST",f"/cases/{cid}/payment/claim",tok); taps+=1; rec["claim"]=st
        st,cf=smoke("POST",f"/smoke/cases/{cid}/payment/confirm"); rec["confirm"]=st; tp=time.time(); rec["t_paid"]=t()
        if st!=200: raise SystemExit(f"confirm {st} {cf}")
        a=None
        for i in range(240):
            st,cs,dt=call("GET",f"/cases/{cid}",tok)
            if cs.get("actions"):
                a=cs["actions"][0]
                if a.get("downloadable") or a.get("approval_status")=="pending": break
            time.sleep(0.5)
        rec["paid_to_doc_s"]=round(time.time()-tp,1); rec["t_doc"]=t()
        if not a: raise SystemExit("нет документа 120 с после оплаты")
        rec["action"]={k:a.get(k) for k in ("action_id","title","status","approval_status","downloadable","has_pdf")}
        taps+=1
        for fmt in ("docx","pdf"):
            r2=S.get(f"{A}/cases/{cid}/actions/{a['id']}/document?format={fmt}",headers={"Authorization":f"Bearer {tok}"},timeout=60)
            rec[f"dl_{fmt}"]=[r2.status_code,r2.headers.get("content-type","")[:40],len(r2.content)]
            if r2.status_code==200: open(f"doc-{len(out)}.{fmt}","wb").write(r2.content)
        rec["taps"]=taps; rec["case_id"]=cid
    except SystemExit as e: rec["fail"]=str(e)
    except Exception as e: rec["fail"]=repr(e)[:200]
    rec["t_total"]=t(); out.append(rec); print(json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=="__main__": json.dump(out,open(sys.argv[1],"w"),ensure_ascii=False,indent=1)
