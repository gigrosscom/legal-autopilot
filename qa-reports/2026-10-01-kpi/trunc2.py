from sim import *
import os,sys,re
ST=os.environ["SMOKE_TOKEN"]
r=S.get(A+"/examples",params={"lang":"ru","limit":"4"},timeout=30); ex=r.json().get("examples",[]) if r.ok else []
print("examples",r.status_code,ex)
Q=ex[:4]+["Kaspi списал деньги за подписку, хотя оплата была без моего согласия. Как вернуть?","Жұмыс беруші екі ай жалақы төлемеді, не істеймін?","Ақаулы тауар үшін ақшаны қалай қайтарамын?","Бала туғанда қандай жәрдемақы беріледі?","Көршім пәтерімді су басты, шығынды қалай өндіремін?","Банк келісімімсіз ақша шешіп алды, не істеу керек?","Работодатель не выплатил зарплату за два месяца, что делать?","Банк списал деньги без моего согласия, что делать?","Меня уволили без предупреждения, законно ли это?","Бывший муж не платит алименты, как взыскать?","Пришёл штраф с камеры, но за рулём был не я. Как обжаловать?","Арендодатель не возвращает залог за квартиру, что делать?"]
out=[]
for q in Q:
    tok=S.post(A+"/smoke/user",headers={"X-Smoke-Token":ST}).json()["token"]
    st,c,dt=call("POST","/cases",tok,json={"text":q,"language":("kk" if re.search("[әғқңөұүһі]",q) else "ru"),"country":"KZ","accept_terms":True,"defer":True}); cid=c["case"]["id"]
    res=chat(tok,cid,q,("kk" if re.search("[әғқңөұүһі]",q) else "ru")); raw=res.get("text") or ""
    st,h,dt=call("GET",f"/cases/{cid}/chat",tok); saved=[m["text"] for m in h if m["role"]=="assistant"]; saved=saved[-1] if saved else ""
    t=re.sub(r"\[?\[\s*(MORE|DOCUMENT)\s*\]\]?","",saved).strip()
    last=t.rstrip()[-1:] if t else ""
    ends_ok=last in ".?!…»)\"" or t.rstrip().endswith(("**",")"))
    empty_items=len(re.findall(r"^\s*(\d+\.|[-*•])\s*$",t,re.M))
    broken=bool(re.search(r"[а-яёa-z]{1,3}$",t.rstrip())) and not ends_ok
    out.append({"q":q,"ttft":res.get("ttft"),"total":res.get("total"),"chars":len(t),"ends_ok":ends_ok,"empty_items":empty_items,"tail":t[-80:],"stream_vs_saved":len(raw.replace("[[MORE]]","").replace("[[DOCUMENT]]","").strip())-len(t)})
    o=out[-1]; print(("✅" if ends_ok and not empty_items and t else "❌"),o["ttft"],o["total"],o["chars"],"пустых пунктов",empty_items,"|",q[:45],"| …",repr(o["tail"][-45:]),flush=True)
json.dump(out,open(sys.argv[1],"w"),ensure_ascii=False,indent=1)
bad=[o for o in out if not o["ends_ok"] or o["empty_items"] or not o["chars"]]
import statistics as s
print(f"ИТОГ: обрезано/битых {len(bad)} из {len(out)} · первые слова медиана {s.median([o['ttft'] for o in out if o['ttft']])} с · полный ответ медиана {s.median([o['total'] for o in out if o['total']])} с")
