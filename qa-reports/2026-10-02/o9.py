# O9: после «Да, покажите» чат не должен выдавать весь текст документа бесплатно; кнопка «Составить документ» (offer_document) должна оставаться.
import os,time,json
from sim import S,A,call,chat
ST=os.environ["SMOKE_TOKEN"]
smp=lambda m,p,tok=None,b=None:S.request(m,A+p,headers=({"X-Smoke-Token":ST}|({"Authorization":f"Bearer {tok}"} if tok else {})),json=b,timeout=90)
Q=["Купил холодильник за 380000 тг в «Мечта» 05.09.2026, не морозит, отказ в возврате. Составьте претензию.",
   "Работодатель не выплатил зарплату за 2 месяца, 600 000 тг. Составьте документ.",
   "Арендодатель не возвращает депозит 180 000 тг за квартиру. Составьте претензию."]
# маркеры «текста документа» в ответе чата
DOCMARK=["ПРЕТЕНЗИЯ","ЗАЯВЛЕНИЕ","ИСКОВОЕ","Кому:","От:","На основании изложенного","ПРОШУ","Дата:","Подпись"]
bad=0; out=[]
for q in Q:
    tok=smp("POST","/smoke/user").json()["token"]
    cid=call("POST","/cases",tok,json={"text":"QA-TEST team-test. "+q,"language":"ru","country":"KZ","accept_terms":True,"defer":True})[1]["case"]["id"]
    chat(tok,cid,"QA-TEST. "+q,"ru")
    r=chat(tok,cid,"Да, покажите","ru"); txt=r.get("text") or ""
    # offer_document в последнем сообщении бота
    h=call("GET",f"/cases/{cid}/chat",tok)[1]
    last_bot=[m for m in h if m["role"]=="assistant"][-1] if any(m["role"]=="assistant" for m in h) else {}
    offer=last_bot.get("offer_document")
    hits=[m for m in DOCMARK if m in txt]
    # «весь текст документа» = много маркеров подряд (шапка Кому/От + ПРОШУ/На основании)
    dump = ("ПРОШУ" in txt or "На основании изложенного" in txt) and ("Кому:" in txt or "От:" in txt)
    ok = (not dump) and bool(offer)
    if not ok: bad+=1
    out.append({"q":q[:40],"chars":len(txt),"doc_markers":hits,"dump_full_doc":dump,"offer_document":offer,"ok":ok})
    print(("✅" if ok else "❌"),q[:42],"| символов",len(txt),"| маркеры",hits,"| вывалил документ:",dump,"| кнопка:",offer,flush=True)
json.dump(out,open("o9.json","w"),ensure_ascii=False,indent=1)
print("ИТОГ O9: плохих",bad,"из",len(Q))
