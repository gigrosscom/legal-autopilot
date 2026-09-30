from intake import *
from cl import CL
out=[]
for name,lang,msgs in CL[:13]:
    rec={"client":name}
    try:
        st,u,dt=call("POST","/users",json={"language":lang,"country":"KZ","src":"qa-test"}); tok=u["token"]
        st,c,dt=call("POST","/cases",tok,json={"text":"QA-TEST. "+msgs[0]+" "+msgs[1],"language":lang,"country":"KZ","accept_terms":True})
        rec["create"]=[st,dt]; cid=c["case"]["id"]; rec.update(tok=tok,cid=cid)
        cs,log=drive(tok,cid,25)
        rec["steps"]=len(log); rec["log"]=log
        rec["final"]={k:cs.get(k) for k in ("status","stage","question","actions","proposal","payment","plan","needs_review","safety","scenario")}
        st,p,dt=call("POST",f"/cases/{cid}/payment",tok,json={"purpose":"document"}); rec["pay"]=[st,p]
    except Exception as e: rec["exc"]=repr(e)[:300]
    out.append(rec); json.dump(out,open("intake.json","w"),ensure_ascii=False,indent=1)
    f=rec.get("final",{}); print(name,"steps",rec.get("steps"),"create",rec.get("create"),"status",f.get("status"),"q",(f.get("question") or {}).get("field"),"prop",(f.get("proposal") or {}).get("type"),"actions",len(f.get("actions") or []),"pay",rec.get("pay",[None])[0],rec.get("exc",""),flush=True)
