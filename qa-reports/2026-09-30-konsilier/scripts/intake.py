from sim import *
import re
def answer_for(q):
    f=q.get("field",""); typ=q.get("type"); opts=q.get("options") or []
    if typ=="evidence": return "Пропустить"
    if opts: 
        o=opts[0]; return o.get("value") or o.get("label") if isinstance(o,dict) else str(o)
    if typ=="email" or "email" in f: return "пропустить" if q.get("optional") else "test@example.com"
    if "address" in f: return "г. Алматы, ул. Абая, 1"
    if typ in ("date",) or "date" in f: return "20.09.2026"
    if "amount" in f or typ=="money": return "250000"
    if "name" in f or "respondent" in f or "seller" in f or "employer" in f: return "ТОО «Тест-Компания», БИН 123456789012"
    if "address" in f: return "г. Алматы, ул. Абая, 1"
    if "phone" in f: return "+7 701 000 00 00"
    if "iin" in f: return "Пропустить"
    return "Пропустить" if q.get("optional") else "Подробности: товар не работает, продавец отказал устно 25.09.2026"
def drive(tok,cid,maxsteps=18):
    log=[]
    for i in range(maxsteps):
        st,cs,dt=call("GET",f"/cases/{cid}",tok)
        q=cs.get("question"); 
        if cs.get("status")!="intake" or not q or (cs.get("proposal") or {}).get("type") not in (None,"none"):
            return cs,log
        a=answer_for(q)
        st,r,dt=call("POST",f"/cases/{cid}/messages",tok,json={"text":a})
        rep=(r.get("reply") or {}) if isinstance(r,dict) else {}
        log.append({"field":q.get("field"),"type":q.get("type"),"q":q.get("text","")[:120],"a":a,"st":st,"dt":dt,"reply":(rep.get("message") or "")[:160],"err":rep.get("error") or (r if st>=400 else None)})
        if st>=400: return (r if isinstance(r,dict) else {}),log
        cs=r.get("case",cs)
    return cs,log
if __name__=="__main__":
    d=json.load(open("c1.json")); cs,log=drive(d["tok"],d["cid"])
    for l in log: print(l)
    for k in ["status","status_label","stage","question","actions","proposal","payment","plan","needs_review","safety"]: print(k,":",json.dumps(cs.get(k),ensure_ascii=False)[:500])
