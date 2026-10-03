from build import build
c=lambda n,h,p:f'<div class="c"><div class="n">{n}</div><h3>{h}</h3><p>{p}</p></div>'
k=lambda h,p:f'<div class="c"><h3>{h}</h3><p>{p}</p></div>'
st=lambda b,l,s:f'<div class="c"><div class="big">{b}</div><div class="lbl">{l}</div><div class="src">{s}</div></div>'
T={'title':'Pitch Deck','foot':'AI assistant for legal questions',
'cover':{'tag':'Pre-seed $500,000 · October 2026','ey':'Our mission','h':'Free a billion people from legal helplessness','sub':'The law should work for everyone — not only for those who can afford a lawyer.','l':'konsilier.com · web, phone app, Telegram','r':'Konsilier AI LLP · dev@konsilier.com'},
'slides':[
('Problem','Millions of people face the law alone',
 '<div class="g g3">'+k('Expensive','A lawyer in Almaty charges KZT 4,200–25,000 for a claim letter and KZT 100–250k for court. For a KZT 30k dispute it does not pay off.')+k('Confusing','Laws are written in complex language. People know neither their rights, nor where to go, nor the deadline.')+k('Slow','Finding a lawyer, meetings, waiting — days and weeks, while the legal deadlines keep running.')+'</div>'
 '<div class="g g3" style="margin-top:18px">'+st('83.8k','consumer complaints to the regulator in 2025','Konsilier GTM, 03.10.2026')+st('232,758','child-support debtors in H1 2026','Tengrinews')+st('2.1M','small businesses — counterparties that do not pay','stat.gov.kz')+'</div>'),
('Solution','Three clicks from problem to action',
 '<div class="g g4">'+c(1,'Describe it','In plain words, by text or voice. Konsi asks follow-up questions like a person.')+c(2,'Understand your rights — free','A short answer and steps 1-2-3 grounded in the official text of the law.')+c(3,'Get the document','Claim, complaint, application or lawsuit — ready PDF and Word with your data and calculation.')+c(4,'Sign and send','E-signature, delivery to the other party, "where and to whom", deadline tracking.')+'</div>'
 '<div class="g g2" style="margin-top:18px">'+k('Need court? — "Find a lawyer"','The case is already assembled: lawyers respond, the client chooses. Free for the client.')+k('Where it runs','Web app, phone app (PWA), Telegram. Russian and Kazakh.')+'</div>'
 '<div class="note">Free to understand. Paid to act.</div>'),
('Key difference','Grounded in law — not a chatbot',
 '<div class="g g3">'+k('Norms only from the law','Articles and deadlines come from the official text (adilet.zan.kz). No article — it is flagged; the AI does not invent.')+k('Rules in code','Documents are drafted by Anthropic Claude under scenario rules. Mandatory rules are checked against Kazakh law, encoded and covered by tests. A scenario engine — not the model — picks the route.')+k('Every document is checked','Correct parties, amounts in tenge, no empty fields. Personal data is de-identified before it reaches a model.')+'</div>'
 '<div class="g g3" style="margin-top:18px">'+k('Free chat','40 messages a day, text and voice.')+k('20+ Kazakhstan scenarios','Consumer, debt, employment, housing, utilities, government, family.')+k('Deadline tracking','The app remembers dates and reminds until the case is done.')+'</div>'),
('Marketplace','Two-sided platform: client and lawyer',
 '<div class="g g2">'+k('Client','Question → free analysis → "Document" KZT 2,990 or "Document package" KZT 9,990 → optional "Find a lawyer" (free) → responses → choose a lawyer. The client pays the lawyer\'s fee directly.')+k('Lawyer','Tokens: 1 token = KZT 1,000, packs from 10. Response to a case — 1 token; a case won — 10/20/30/40 tokens by claim value. Paid before contact, not a fee share — bypassing the platform does not reduce our revenue.')+'</div>'
 '<div class="g g3" style="margin-top:18px">'+st('KZT 17,400','revenue per lawyer case — 5.8× a document','13,400 per case + 4 responses')+st('2–7%','of the lawyer\'s fee — what a case costs them','fees KZT 200k – 3M')+st('KZT 15–115k','what a client costs a lawyer today (ads, 2GIS)','marketing estimate')+'</div>'),
('Unit economics','≈ 99% of every sale stays with us',
 '<div class="g g4">'+st('≈ 99%','kept after Kaspi\'s 0.95% fee','the only variable cost')+st('≈ KZT 306','value of one visit — the ceiling for cost per click','0.5 × (3% × 2,990 + 3% × 17,400)')+st('≥ 34','lawyer LTV / CAC','LTV ≈ KZT 689k, CAC KZT 0–20k')+st('12','documents a month — break-even today','fixed costs KZT 32,940 / month')+'</div>'
 '<table><tr><th>Monthly scenario (estimate)</th><th>Base</th><th>Growth</th><th>Scale</th></tr><tr><td>Visits</td><td>13,000</td><td>43,000</td><td>130,000</td></tr><tr><td>Paid documents / lawyer cases</td><td>195 / 195</td><td>645 / 645</td><td>1,950 / 1,950</td></tr><tr><td>Active lawyers</td><td>≈ 50</td><td>≈ 160</td><td>≈ 490</td></tr><tr><td><b>Revenue</b></td><td><b>KZT 3.98M</b></td><td><b>KZT 13.15M</b></td><td><b>KZT 39.76M</b></td></tr></table>'
 '<div class="src" style="margin-top:10px">Conversions are estimates, to be replaced by facts two weeks after launch. Source: "Konsilier — business model and unit economics", 04.10.2026.</div>'),
('Market & go-to-market','Prove it in Kazakhstan — scale to the world',
 '<div class="ph" style="margin-top:30px"><div class="h">Now</div><div><b>Kazakhstan</b> — test market: 19.2M internet users (92.9%, DataReportal). Launched 02.10.2026.</div><div>Organic, zero ad budget: WhatsApp, Telegram groups, Facebook groups, referrals (K ≥ 0.3), accountant partners, SEO scenario pages. First 50 lawyers via an account manager.</div>'
 '<div class="h">Next</div><div><b>Europe and the US</b> — main markets.</div><div>Same engine; a country pack adds law, scenarios and language.</div>'
 '<div class="h">Then</div><div><b>Australia, Canada, Japan, Southeast Asia.</b></div><div>A new country is data and local lawyers, not a rebuild.</div></div>'),
('Traction','First days after launch',
 '<div class="g g4">'+st('66','users','fact, 02.10.2026')+st('33','cases opened — 50% of visits','fact, 02.10.2026')+st('0','payments — product first, then traffic','decision, 03.10.2026')+st('20+','Kazakhstan scenarios to a finished document','konsilier.com')+'</div>'
 '<div class="ph" style="margin-top:26px;grid-template-columns:150px 1fr"><div class="h">29.09.2026</div><div>Konsilier AI LLP incorporated in Almaty</div><div class="h">30.09.2026</div><div>Applied to NVIDIA Inception</div><div class="h">02.10.2026</div><div>Public launch in Kazakhstan</div><div class="h">Next</div><div>Lawyer tokens and case feed → traffic → conversion facts in two weeks</div></div>'),
('Technology','Konsilier LM — our own legal model',
 '<div class="g g4">'+k('Open base LLM','2–4 candidates compared on our closed tests; licence and Russian/Kazakh quality.')+k('Adapted weights','SFT and LoRA on verified examples — legal method and answer format.')+k('Legal corpus & RAG','Norms with versions and dates; retrieval filters by country and date; answers cite sources.')+k('Konsilier Bench','Closed gold set, questions verified by a lawyer; release only when thresholds pass.')+'</div>'
 '<div class="ph" style="margin-top:22px;grid-template-columns:260px 1fr"><div class="h">1–2 weeks</div><div>Audit and pilot scope: one country, one scenario</div><div class="h">2–4 weeks</div><div>Base model chosen on Konsilier Bench</div><div class="h">4–10 weeks</div><div>Corpus and benchmark (in parallel)</div><div class="h">3–6 months</div><div>Limited pilot of Konsilier LM 1 with lawyers</div></div>'
 '<div class="src" style="margin-top:8px">Source: "Step-by-step plan for our own legal language model", 03.10.2026. Timelines are planning estimates.</div>'),
('Competition','Konsilier vs the alternatives',
 '<table><tr><th>Criterion</th><th class="us">Konsilier</th><th>Lawyer</th><th>General AI</th><th>Templates</th></tr>'
 '<tr><td>Price per document</td><td class="us">from KZT 2,990</td><td>KZT 4,200–25,000</td><td>—</td><td>cheap</td></tr>'
 '<tr><td>Time</td><td class="us">minutes</td><td>days</td><td>minutes</td><td>minutes</td></tr>'
 '<tr><td>Grounded in law</td><td class="us">official text</td><td>yes</td><td>may invent</td><td>outdated</td></tr>'
 '<tr><td>Fits your situation</td><td class="us">yes</td><td>yes</td><td>partly</td><td>no, a blank</td></tr>'
 '<tr><td>E-signature and sending</td><td class="us">yes</td><td>via lawyer</td><td>no</td><td>no</td></tr>'
 '<tr><td>Deadline tracking</td><td class="us">yes</td><td>manual</td><td>no</td><td>no</td></tr>'
 '<tr><td>Lawyer if court is needed</td><td class="us">responses to an assembled case</td><td>—</td><td>no</td><td>no</td></tr></table>'),
('Team','Two founders, operations run by AI agents',
 '<div class="g g2">'+k('Nurlan Khabibulla','Founder & CTO. Designed and built the product end to end.')+k('Saltanat Tulegenova','CEO, director of the LLP. Lawyer.')+'</div>'
 '<div class="c" style="margin-top:18px"><h3>AI team</h3><p>Product manager, developer, integrations, QA, documentation, finance, marketing, brand-risk manager, AI legal agent. Founders approve every spend, publication and outbound message.</p>'
 '<span class="pill">Plan in 6 months: 9 people</span><span class="pill">4 ML engineers</span><span class="pill">3 account managers</span></div>'),
('Ask','Raising $500,000 pre-seed',
 '<div class="g g3">'+k('Konsilier LM','GPUs and model training, corpus and Konsilier Bench — servers and GPUs ≈ KZT 0.9M a month.')+k('Team and office','9 people: CEO, 4 ML engineers, 3 account managers, accountant. ≈ KZT 10.1M a month; one-off ≈ KZT 7–8.5M.')+k('Go-to-market','50 → 490 active lawyers, then the first EU/US market. Team break-even ≈ 590 lawyer cases a month.')+'</div>'
 '<p class="lead" style="margin-top:22px">Join us to free a billion people from legal helplessness.</p><div class="note" style="font-size:22px">dev@konsilier.com · konsilier.com</div>'),
]}
build(T,'en','konsilier-pitch-final-en.html')
