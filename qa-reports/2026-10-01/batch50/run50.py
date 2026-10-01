import os,sys,time,json,re
from sim import S, A, call, chat
import evidence as EV
from cases50 import C
ST=os.environ["SMOKE_TOKEN"]
def sm(m,p,tok=None,body=None):
    h={"X-Smoke-Token":ST}
    if tok: h["Authorization"]=f"Bearer {tok}"
    r=S.request(m,A+p,headers=h,json=body,timeout=90)
    try: return r.status_code,r.json()
    except Exception: return r.status_code,r.text[:200]
def upload(tok,cid,kind,path,ctype):
    fn=os.path.basename(path)
    r=S.post(f"{A}/cases/{cid}/evidence",headers={"Authorization":f"Bearer {tok}"},
             files={"file":(fn,open(path,"rb"),ctype)},data={"kind":kind},timeout=120)
    return r.status_code
IIN="900101300017"
def val_for(f,typ=None):
    f=f or ""
    if "iin" in f or "bin" in f: return IIN if "iin" in f else "050140001238"
    if typ=="email" or "email" in f: return "test@example.com"
    if typ=="phone" or "phone" in f: return "+77010000000"
    if typ=="date" or "date" in f: return "20.09.2026"
    if "name" in f and "applicant" in f: return "Тестов Тест Тестович"
    if "name" in f or "respond" in f or "seller" in f or "employer" in f or "contractor" in f or "landlord" in f: return "ТОО «Тест-Ответчик»"
    if "address" in f: return "г. Алматы, ул. Абая, 1, кв. 5"
    if typ=="money" or "amount" in f or "sum" in f: return "100000"
    return "Тест"
def fill(tok,cid,fields):
    """fields — список полей (строки или {field,type}) от draft.blanks или payment 422."""
    vals={}
    for b in fields or []:
        if isinstance(b,dict): vals[b.get("field")]=val_for(b.get("field"),b.get("type"))
        else: vals[b]=val_for(b)
    vals={k:v for k,v in vals.items() if k}
    if not vals: return 200,{}
    st,r,dt=call("POST",f"/cases/{cid}/facts",tok,json={"values":vals})
    if st>=400:  # пачка отклонена — по одному полю, чтобы одно плохое не блокировало остальные
        for k,v in vals.items(): call("POST",f"/cases/{cid}/facts",tok,json={"values":{k:v}})
        st=200
    return st,r
def run_one(c):
    t0=time.time(); taps=0; rec={"code":c["code"],"sc_expected":c["sc"],"lang":c["lang"],"prod":c["prod"],"docs_n":len(c["docs"])}
    def T(): return round(time.time()-t0,1)
    try:
        st,u=sm("POST","/smoke/user"); 
        if st!=200: raise RuntimeError(f"smoke/user {st}")
        tok=u["token"]
        st,cc,dt=call("POST","/cases",tok,json={"text":"QA-TEST team-test. "+c["story"],"language":c["lang"],"country":"KZ","accept_terms":True,"defer":True})
        if st>=400: raise RuntimeError(f"cases {st} {cc}")
        cid=cc["case"]["id"]; rec["case"]=cid; taps+=1
        r=chat(tok,cid,"QA-TEST. "+c["story"],c["lang"]); rec["ttft"]=r.get("ttft"); rec["ans_chars"]=len(r.get("text") or "")
        for kind,kindf,name,lines in c["docs"]:
            path,ctype=(EV.png if kindf=="png" else EV.txt)(name,lines)
            us=upload(tok,cid,kind,path,ctype); taps+=1; rec.setdefault("uploads",[]).append(us)
        cs=None
        for i in range(24):
            st,cs,dt=call("GET",f"/cases/{cid}",tok)
            if cs.get("status")=="qualified" or (cs.get("scenario") and cs.get("status")!="intake"): break
            time.sleep(1.5)
        if not (cs.get("scenario")) and cs.get("status")=="intake" and not cs.get("question"):
            chat(tok,cid,"Да, помогите подготовить нужный документ.",c["lang"])  # добить классификацию
            for i in range(12):
                st,cs,dt=call("GET",f"/cases/{cid}",tok)
                if cs.get("scenario"): break
                time.sleep(1.5)
        rec["sc_got"]=(cs.get("scenario") or {}).get("id"); rec["status_after_chat"]=cs.get("status")
        taps+=1
        guard=0
        while cs.get("status")=="intake" and cs.get("question") and guard<12:
            q=cs["question"]; typ=q.get("type")
            ans="Пропустить" if typ=="evidence" or q.get("optional") else ("20.09.2026" if typ=="date" else IIN if "iin" in q.get("field","") else "г. Алматы, ул. Абая, 1" if "address" in q.get("field","") else "ТОО «Тест-Ответчик»" if ("name" in q.get("field","") or "respond" in q.get("field","")) else "Подробности в описании выше.")
            st,rr,dt=call("POST",f"/cases/{cid}/messages",tok,json={"text":ans}); guard+=1; taps+=1
            cs=rr.get("case",cs) if isinstance(rr,dict) else cs
            if st>=400: break
        rec["questions"]=guard
        st,dr,dt=call("GET",f"/cases/{cid}/draft",tok); rec["draft"]=st; rec["t_draft"]=T() if st==200 else None
        if cs.get("status")!="qualified":
            rec["result"]="тупик: нет документа"; rec["status_final"]=cs.get("status"); rec["t_total"]=T(); return rec
        blanks=(dr.get('blanks') or []) if isinstance(dr,dict) else []
        if blanks: fill(tok,cid,blanks)
        st,nx,dt=call("POST",f"/cases/{cid}/actions/next",tok,json={})
        st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":c["prod"]}); taps+=1
        for _ in range(3):
            if not (st==422 and isinstance(pp,dict) and (pp.get("detail") or {}).get("code") in ("applicant_data_required","invalid_facts")): break
            need=(pp["detail"].get("fields") or [])
            fst,fr=fill(tok,cid,need)
            if fst==422 and isinstance(fr,dict) and (fr.get("detail") or {}).get("code")=="invalid_facts":
                # поле не прошло проверку — заполнить заново по типам из ответа
                bad=(fr["detail"].get("fields") or {})
                fill(tok,cid,[{"field":k} for k in bad])
            st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":c["prod"]})
        rec["pay_status"]=st
        if st>=400: rec["pay_err"]=pp
        p=(pp.get("case") or {}).get("payment",{}) if isinstance(pp,dict) else {}
        rec["invoice"]={"amount":p.get("amount"),"currency":p.get("currency"),"code":p.get("code"),"invoice_id":p.get("invoice_id"),"ways":[w.get("id") for w in p.get("ways") or []]}
        rec["t_invoice"]=T()
        st,cl,dt=call("POST",f"/cases/{cid}/payment/claim",tok); rec["claim"]=st
        st,cf=sm("POST",f"/smoke/cases/{cid}/payment/confirm"); rec["confirm"]=st; tp=time.time()
        if st!=200: rec["result"]=f"оплата не подтверждена ({st})"; rec["t_total"]=T(); return rec
        acts=[]
        for i in range(80):
            st,cs,dt=call("GET",f"/cases/{cid}",tok)
            acts=cs.get("actions") or []
            if acts and (acts[0].get("downloadable") or acts[0].get("approval_status")=="pending"): break
            time.sleep(0.5)
        rec["paid_to_doc_s"]=round(time.time()-tp,1); rec["t_doc"]=T()
        if not acts: rec["result"]="нет документа 40с после оплаты"; rec["t_total"]=T(); return rec
        act=acts[0]; rec["doc_title"]=act.get("title"); rec["downloadable"]=act.get("downloadable"); rec["approval"]=act.get("approval_status")
        dls={}
        for fmt in ("pdf","docx"):
            r2=S.get(f"{A}/cases/{cid}/actions/{act['id']}/document?format={fmt}",headers={"Authorization":f"Bearer {tok}"},timeout=90)
            dls[fmt]=[r2.status_code,len(r2.content)]
        rec["download"]=dls
        rm=cs.get("roadmap") or {}; pl=cs.get("plan") or {}; dl=act.get("deadline") or (cs.get("deadline") or {})
        steps=rm.get("steps") if isinstance(rm,dict) else None
        rec["roadmap_steps"]=len(steps) if isinstance(steps,list) else bool(rm)
        rec["next_action"]=(cs.get("proposal") or {}).get("title") or (act.get("filing") or {}).get("kind") or act.get("channel")
        rec["deadline"]=dl.get("due_date") if isinstance(dl,dict) else None
        rec["has_roadmap"]=bool(rm); rec["has_plan"]=bool(pl)
        ok = act.get("downloadable") and dls.get("pdf",[0])[0]==200 and dls.get("docx",[0])[0]==200
        if act.get("approval_status")=="pending":
            rec["result"]="✅ на проверке владельца"  # политика 30.09: документ готов, файл откроется после одобрения
        elif ok and rec["roadmap_steps"]:
            rec["result"]="✅ документ+карта"
        elif ok:
            rec["result"]="✅ документ"
        else:
            rec["result"]="⚠️ документ без скачивания"
        rec["case_paid"]=(cs.get("payment") or {}).get("case_paid")
    except Exception as e:
        rec["result"]="ошибка"; rec["error"]=repr(e)[:200]
    rec["taps"]=taps; rec["t_total"]=T(); return rec

OUT=sys.argv[1] if len(sys.argv)>1 else "run50.json"
res=[]
start=int(sys.argv[2]) if len(sys.argv)>2 else 0
end=int(sys.argv[3]) if len(sys.argv)>3 else len(C)
for c in C[start:end]:
    r=run_one(c); res.append(r); time.sleep(3)
    json.dump(res,open(OUT,"w"),ensure_ascii=False,indent=1)
    print(f"{r['code']} {r.get('result','?'):<22} sc={r.get('sc_got')} инв={r.get('invoice',{}).get('amount')} опл→док={r.get('paid_to_doc_s')} всего={r.get('t_total')} док={r.get('doc_title','')[:30]} карта={r.get('roadmap_steps')} срок={r.get('deadline')} {r.get('error','')}",flush=True)
