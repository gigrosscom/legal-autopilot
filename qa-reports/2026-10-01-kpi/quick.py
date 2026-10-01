from sim import *
import os,sys
ST=os.environ["SMOKE_TOKEN"]; R={}
def sm(m,p,tok=None,body=None):
    h={"X-Smoke-Token":ST}; 
    if tok: h["Authorization"]=f"Bearer {tok}"
    r=S.request(m,A+p,headers=h,json=body,timeout=60)
    try: return r.status_code,r.json()
    except Exception: return r.status_code,r.text[:200]
T0=time.time(); t=lambda: round(time.time()-T0,1)
st,u=sm("POST","/smoke/user"); tok=u["token"]; R["user"]=st
st,c,dt=call("POST","/cases",tok,json={"text":"QA-TEST team-test. Купил холодильник за 380000 тенге в «Мечта» 05.09.2026, не морозит, отказ в возврате. Составьте претензию.","language":"ru","country":"KZ","accept_terms":True,"defer":True}); cid=c["case"]["id"]
r=chat(tok,cid,"QA-TEST. Купил холодильник за 380000 тенге в «Мечта» 05.09.2026, не морозит, отказ в возврате. Составьте претензию."); R["chat"]={"ttft":r.get("ttft"),"chars":len(r.get("text","")),"offer":"[[DOCUMENT]]" in r.get("text","")}
for i in range(15):
    st,cs,dt=call("GET",f"/cases/{cid}",tok)
    if cs.get("status")=="qualified": break
    time.sleep(1.5)
st,dr,dt=call("GET",f"/cases/{cid}/draft",tok); R["draft"]=[st,t()]
st,ff,dt=call("POST",f"/cases/{cid}/facts",tok,json={"values":{"applicant_name":"Тестов Тест","applicant_address":"г. Алматы, ул. Абая, 1","applicant_phone":"+77010000000","seller_address":"г. Астана, ул. Мечты, 5"}}); R["facts"]=st
st,nx,dt=call("POST",f"/cases/{cid}/actions/next",tok,json={})
st,pp,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":"document"}); p=(pp.get("case") or {}).get("payment") if isinstance(pp,dict) else pp
R["payment"]={"st":st,"t":t(),**({k:p.get(k) for k in ("amount","currency","status","method","code","ways","way","kaspi_phone","recipient_name","available")} if isinstance(p,dict) else {"raw":str(pp)[:300]})}
st,me=sm("GET","/me",tok); R["me_before"]={k:me.get(k) for k in ("display_name","identities")} if isinstance(me,dict) else me
st,am=sm("GET","/auth/methods"); R["auth_methods"]=am
st,em=sm("POST","/smoke/email",tok,{"email":f"delivered+qa{int(time.time())}@resend.dev"}); R["smoke_email"]=[st,str(em)[:200]]
st,me=sm("GET","/me",tok); R["me_after"]=me
st,cl,dt=call("POST",f"/cases/{cid}/payment/claim",tok); st2,cf=sm("POST",f"/smoke/cases/{cid}/payment/confirm"); tp=time.time(); R["claim"]=[st,None if st<400 else cl]; R["confirm"]=[st2,str(cf)[:300] if st2>=400 else (cf.get("case") or {}).get("payment",{}).get("status")]; open("quick_tok.txt","w").write(tok+" "+cid)
for i in range(60):
    st,cs,dt=call("GET",f"/cases/{cid}",tok)
    if cs.get("actions") and (cs["actions"][0].get("downloadable") or cs["actions"][0].get("approval_status")=="pending"): break
    time.sleep(0.5)
a=(cs.get("actions") or [{}])[0]; R["case_after"]={k:cs.get(k) for k in ("status","stage","needs_review")}|{"pay":(cs.get("payment") or {}).get("status"),"actions":[{k:x.get(k) for k in ("action_id","status","approval_status","downloadable")} for x in cs.get("actions") or []]}; R["doc"]={"paid_to_doc":round(time.time()-tp,1),"t":t(),"downloadable":a.get("downloadable")}
for fmt in ("pdf","docx"):
    r2=S.get(f"{A}/cases/{cid}/actions/{a.get('id')}/document?format={fmt}",headers={"Authorization":f"Bearer {tok}"},timeout=60); R["dl_"+fmt]=[r2.status_code,len(r2.content)]
for path in ["/","/start","/ops","/account","/documents"]:
    r3=S.get("https://konsilier.com"+path,timeout=30); R["page"+path]=r3.status_code
R["case"]=cid
print(json.dumps(R,ensure_ascii=False,indent=1))
json.dump(R,open(sys.argv[1],"w"),ensure_ascii=False,indent=1)
