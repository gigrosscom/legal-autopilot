import requests, json, time, sys, os
A="https://api.konsilier.com/v1"
S=requests.Session(); from requests.adapters import HTTPAdapter; from urllib3.util.retry import Retry; S.mount("https://",HTTPAdapter(max_retries=Retry(total=4,backoff_factor=2,allowed_methods=None,status_forcelist=[]))); S.verify=os.environ.get("REQUESTS_CA_BUNDLE","/root/.ccr/ca-bundle.crt")
def call(m,p,tok=None,**kw):
    h={"Authorization":f"Bearer {tok}"} if tok else {}
    t=time.time(); r=S.request(m,A+p,headers=h,timeout=120,**kw)
    try: body=r.json()
    except Exception: body=r.text[:500]
    return r.status_code, body, round(time.time()-t,2)
def chat(tok,cid,text,lang="ru"):
    t=time.time(); first=None; out=[]; events=[]
    with S.post(f"{A}/cases/{cid}/chat",headers={"Authorization":f"Bearer {tok}"},json={"text":text,"language":lang},stream=True,timeout=180) as r:
        if r.status_code!=200: return {"status":r.status_code,"body":r.text[:300]}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"): continue
            ev=json.loads(line[5:]); events.append(ev.get("type"))
            if ev.get("type") in ("delta","token","text") and first is None: first=time.time()-t
            for k in ("delta","text","token"):
                if isinstance(ev.get(k),str) and ev.get("type")!="done": out.append(ev[k])
            if ev.get("type")=="error": out.append(f"[ERROR {ev}]")
    return {"status":200,"ttft":round(first,2) if first else None,"total":round(time.time()-t,2),"events":sorted(set(events)),"text":"".join(out),"last":events[-3:]}
if __name__=="__main__":
    st,u,dt=call("POST","/users",json={"language":"ru","country":"KZ","src":"qa-test"}); print(st,u,dt)
    tok=u["token"]
    st,c,dt=call("POST","/cases",tok,json={"text":"QA-ТЕСТ. Купил телефон за 250000 тенге в магазине, через неделю сломался, магазин отказывается вернуть деньги. Что делать?","language":"ru","country":"KZ","accept_terms":True,"defer":True})
    print(st,dt); print(json.dumps(c,ensure_ascii=False)[:3000])
    cid=c["case"]["id"]
    r=chat(tok,cid,"QA-ТЕСТ. Купил телефон за 250000 тенге в магазине, через неделю сломался, магазин отказывается вернуть деньги. Что делать?")
    print(json.dumps(r,ensure_ascii=False)[:3000])
    json.dump({"tok":tok,"cid":cid},open("c1.json","w"))
