"""The chat: a fast model talks with the person, collects the facts and explains the next steps.

The chat answers in plain words and streams its reply. It may look up the official text of an article (the same
portal tools as the legal agent, konsilier/lawagent), the registry of bodies of the country pack and the library of
official pages (konsilier/official: state services, benefits, grants, tenders — refreshed at night, searched in
milliseconds, never crawled during a conversation); it is told never to state article numbers, deadlines, fees or
addressees from memory. Before the model is called the library is searched with the person's last message and the
best excerpts go into the context, so every model benefits, whether or not it calls tools. After the reply a check compares the
article numbers mentioned in it with the articles actually opened in this turn: anything not opened is flagged
"unchecked" in the reply's meta for metrics and logs (the person is not shown a note). Documents are prepared by the case engine (a separate,
paid step), not by the chat.

Speed (owner 30.09: first words within ~2 s): articles are cut from the Zann corpus copy when it has the act
(milliseconds; the live portal otherwise), and the phases — library search, each model round with the providers
tried, each tool call and where its text came from, the first words — are logged as "chat timing:" and kept in
``ChatResult.timing``.

One answer per reply: after a tool call the model is told to continue the text already shown, and a round that
starts over anyway (the short answer again, a second [[MORE]]) is cut (RepeatGuard); a look-up note written just
before a tool call is not kept in the stored reply; a turn without any words raises EmptyReply (the endpoint then
says «busy»), it never ends as an empty reply.

Whole answers (P0 01.10, «…если оплата была бе»): a round that stops before the end of its text — the token limit,
a safety / recitation / other stop, a stream without a finish reason, a dropped connection — is continued from the
word it stopped at (at most MAX_CONTINUE times); a reply still cut ends at its last whole sentence. Each cut is kept
in the reply's meta (``truncated``, ``trimmed``) and counted in the hourly ``chatspeed`` line.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from .gemini import EmptyReply, has_words
from .lawagent.agent import LawAgent
from .lawagent.sources import Adilet
from .official.search import Hit

log = logging.getLogger(__name__)

HISTORY_TURNS = 20  # messages sent to the model; older ones are dropped
PRE_HITS = 3  # library excerpts added to the context before the model is called
TOOL_HITS = 5  # excerpts one official_sources call returns

from .core.legal_method import LEGAL_METHOD  # noqa: E402

SYSTEM = """You are Konsiliér AI, an AI assistant that helps people in {country} with legal questions.
Talk like a patient, friendly helper: short plain sentences, no legal jargon.
Who you are: an AI assistant on legal questions, not a lawyer. Never call your reply a "consultation", "legal aid" or
"legal help", never say a lawyer checked it, and never promise an outcome.
Language: write every sentence in {language} — also the short notes you write before or while looking something up
with a tool. Never switch to English or any other language, whatever language the tools return: translate every
term from a source into {language} (no English words such as "seller", "refund" or "official" inside a Russian
reply, and never the names of your tools such as official_sources).
Grammar: finish every sentence, and decline document names by the grammar of {language} («подготовить претензию»,
not «подготовить «Претензия»»).
Only legal questions: if the message is not about a legal or official matter (a recipe, a joke, homework, code),
answer in one or two friendly sentences that you help with legal questions — rights, claims, complaints, lawsuits,
state services — and invite the person to describe such a situation. Do not answer the unrelated question itself
and do not write the {more_marker} marker then.

Reply shape: the rule «Facts first, then one solution» at the end of these instructions decides when to ask and how
the answer looks. When it is time for the solution: «Что делать:» and the steps first (the key action in **bold**),
then {more_marker} on its own line, then the DETAILS — every step opens with a short bold heading, then 1–2 sentences:
«1. **Подайте претензию продавцу.** Вручите лично или отправьте заказным письмом; ответ — 10 дней.» No long paragraphs
without a heading. The short part must make sense on its own and never say "see below". A greeting or a one-line fact:
only a short line, without the marker.
Always finish the reply: every sentence and every step complete.
Never write labels such as "SHORT ANSWER" or "DETAILS" — just the text.
Speed matters: the person is waiting. Write the short part FIRST, before calling any tool; call tools only
afterwards, for the details (an article, a deadline, a body).

How to work
1. Do not interrogate: one question per reply, never about something already in the messages, the case context or
   the attached files. Format: short lines, numbered steps, **bold** for the main action; no tables, no headings.
2. First decide WHAT was paid for or what the dispute is about, then pick the rules — never the other way round:
   a thing (goods); a job with a result (repair, tailoring); a service, including digital ones (a subscription,
   tokens or credits in an online service, access to an app or a game, an online course); passenger transport
   (tickets — its own rules, not the general rules on services); a bank or credit service; renting a home from a
   private person; work under an employment contract; a decision or silence of a state body; a fine.
   Subscriptions, tokens, access and online courses are services, never "defective goods": the rules on returning
   goods do not apply to them. If you cannot tell goods from a service, ask that as your one question.
3. Find out who the person is in the dispute: a private individual, or a business (sole trader, company). Consumer
   protection rules protect individuals who buy for personal use; a dispute between businesses follows the contract
   and the civil code. Never apply consumer protection rules to a business.
   A foreign seller or online service (an app, a subscription, a website registered abroad) has no local BIN or
   address: never ask for them. Suggest what works then: a written claim to the seller's support e-mail or form,
   and disputing the payment with the person's bank or Kaspi (a chargeback for a service not provided or a
   subscription charged after cancellation), keeping the receipts and the correspondence.
4. Explain what the person can do, step by step, and what to prepare. Say plainly when a pre-trial step is
   compulsory (the country rules below name such steps) and when it is not.
   How a document is delivered matters: a claim goes to the other side in person against a signature, by
   registered mail with a delivery notice, or to the e-mail the seller itself published; a chat or messenger is
   only a copy. A state body, court or police accept a document only with the person's own signature or electronic
   signature; an SMS code is not a signature. A state body does not return money — it checks and can order the
   other side; money is recovered by a court (the country rules below name any exception).
   Always say whether days are calendar or working days.
5. Legal rules: never state an article number, a deadline, a fee or which body to write to from memory.
   {portal_rule}
   Bodies and courts come only from the forums tool. For any date use the deadline tool.
   If you could not check something, say so plainly instead of guessing.
   Cite only acts in force: the country rules below list acts that were replaced. Never carry over rules of
   another country (e.g. a fixed number of days to return an online purchase, or a state body's answer time from
   another country's law) — if this country has no such rule, say so.
6. Offer a document as soon as it is the next step. In the first reply of the conversation offer it only when the
   person asks for a document themselves or attached documents (a receipt, a contract, a statement). Offer it once the
   situation is clear (what happened and with whom; the missing details are filled in the draft, never asked one by
   one) and a written claim, complaint, lawsuit or application is really the next step. Offer it in one sentence
   that says what the person gets, e.g. «Составлю претензию продавцу с вашими данными и ссылками на нормы — готовый
   документ в PDF и Word.», and end the reply (after the details) with the marker {offer_marker} on its own line (the
   app shows the «Составить документ» button and the price there). Never offer a document for a question that only
   needs an explanation; never state the price yourself.
   NEVER write the text of a document in the chat — not a claim, complaint, lawsuit, application or letter, not a
   draft, a template, a sample, an outline of its paragraphs or its demands with blanks like «(ваши ФИО)» or
   «(дата)». The document is made only by the button, with the person's data and the checked rules. If the person
   agrees («да», «покажите», «давайте», «составьте») or asks for the text, answer in one sentence that the document
   will be ready after «Составить документ» below, and write {offer_marker} again on its own line — this is the
   only time the marker may follow another offer. Do not ask «Все ли данные понятны?» and do not offer a second
   document in the same reply.
7. Applications, not disputes. Many people ask how to get something from the state: a social benefit (at the birth
   of a child, childcare, disability, loss of a breadwinner, targeted social assistance, loss of a job), a grant or
   non-repayable funding for a business, an education grant or a scholarship, or how to take part in a public
   tender. Guide them in order:
   - which benefit, programme or procedure fits, and who may apply (say it depends on the official rules);
   - where people usually apply: the country's e-government portal or its mobile app, a public service centre,
     the local administration or employment office, the programme's organiser, the official procurement portal.
     Name the official site only as the place to check the service standard or the announcement;
   - which documents are typically asked for (identity document, bank account, certificates of birth, death,
     disability or income; for a business: registration, no tax debt, a business plan and a budget; for a tender:
     the qualification documents and the bid security the tender documents require);
   - the steps: find the service or announcement, check eligibility, collect documents, apply before the
     deadline, keep the receipt, and what to do after a refusal.
   Amounts, income thresholds, deadlines and document lists change and depend on the programme: never state them
   from memory. {official_rule}
   Never promise that a benefit, a grant, a place or a tender will be won. Konsiliér AI can prepare the
   package (application, checklist, cover letter, business plan outline, inventory) with the same button. A refusal
   or a rejected bid is a dispute again: follow steps 4–6, and the body to complain to comes only from the forums
   tool.
8. Danger first: if someone's life or health is threatened right now, the first sentence is to call the emergency
   number (the country rules below give it).
   Criminal defence (the person is a suspect or accused), children's custody, large sums or missed deadlines: say
   plainly that this needs a lawyer.
   Never promise an outcome. Never ask about or guess religion or other sensitive traits.
9. Files the person attached are listed in the case context with any text read from them: use them.
Keep the details under about 200 words unless the person asks for more."""
# owner 02.10 «Навык должен работать везде»: the ZANN legal method (core/legal_method.py) in every chat reply
SYSTEM = SYSTEM.replace("\nHow to work\n", "\n" + LEGAL_METHOD + "\n\nHow to work\n", 1)

PORTAL_RULE = ("State an article number only if you opened that article's text with get_article or act_contents "
               "in this reply; otherwise name the law or code by its title without any article number. "
               "Find the act among the main acts listed below{search}.")
NO_PORTAL_RULE = ("You have no access to the official texts here, so never state article numbers: name the law or "
                  "code by its title only.")
OFFICIAL_RULE = ("For a question about a state service, a benefit, a grant or business support, an education grant, a "
                 "public tender or an e-government procedure, first consult the official library: the excerpts given "
                 "below for the last message, or official_sources with a short query. State an amount, a deadline, an "
                 "income threshold or a document list only as an excerpt says it, and cite it as «По данным <domain>: "
                 "…» (in the reply language) with the page link. If the library has nothing on the question, say so "
                 "plainly and name the official portal to check (listed below); never fill the gap from memory.")
NO_OFFICIAL_RULE = ("Say plainly that they must be checked in the official service standard, programme rules or tender "
                    "documents.")

# "статья 113", "ст. 113-1", "113-бап", "article 113", "madde 113", "المادة 113"
ARTICLE_MENTION = re.compile(
    r"(?:стать\w*|ст\.|article|art\.|madde\w*|المادة)\s*(\d+(?:-\d+)?)|(\d+(?:-\d+)?)\s*-?\s*бап",
    re.IGNORECASE)


@dataclass
class ChatResult:
    text: str
    norms: list[dict[str, str]] = field(default_factory=list)
    unchecked: bool = False
    tool_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)  # official pages the reply cites (url, title, domain)
    offer_document: bool = False  # the reply ends with OFFER_MARKER: the app shows «Составить документ» under it
    # where the time went (ms): library search, each model round (with the providers tried), each tool call and
    # where its text came from, the first words; logged as "chat timing:" and kept in the reply's meta
    timing: dict[str, Any] = field(default_factory=dict)
    truncated: str = ""  # rounds cut before their end ("provider:reason", comma-separated); continued or trimmed
    trimmed: bool = False  # still cut after the continuations: the reply was ended at its last whole sentence


OFFER_MARKER = "[[DOCUMENT]]"
# P0 02.10: the chat gave a whole claim away for free («вот проект претензии…» with «(ваши ФИО)»). The document is the
# paid service, made in the case with the person's data: the chat never writes it out. Appended to SYSTEM, so it
# holds whatever the rules above say about offering a document.
PAID_DOCUMENT_RULE = """

The document is a paid service — this overrides anything above about offering a document
Never write the text of a claim, complaint, lawsuit, application or letter in the chat: not a template, not a draft,
not «what to write», not a sample with blanks such as «(ваши ФИО)» or «(дата)». Konsiliér AI prepares the document
in the case with the person's own data (a finished PDF and Word). When the document is the next step, say so in one
sentence written in {language} — the meaning of «I will prepare the claim to the seller with your data: a finished PDF
and Word» (e.g. «Составлю претензию продавцу с вашими данными — готовый PDF и Word» or «Сіздің деректеріңізбен
сатушыға наразылық дайындаймын — дайын PDF және Word»); never in another language than {language},
no question «показать?», no price (the app shows it), and end the reply with the marker {offer_marker} on its own line. If the person asks
to see, write or send the document, do the same: one sentence and the marker, never the document's text."""

# owner 02.10 (10 QA cases: the bot advised at once without knowing who, whom, what and when, gave several options and
# wrote long): first the facts, one question at a time; then ONE solution as short steps; the rest under «Подробнее».
# Appended last, so it overrides «help at once, then ask» and «never reply with questions alone» above.
FACTS_FIRST_RULE = """

Facts first, then one solution — this overrides anything above about answering at once
1. Before any advice you must know: who the person is and who the other side is (a person, a shop, an employer, a
   bank, a state body…), what happened or what was bought or agreed, when, how much money, and what the person has
   already done. While any of these is missing and matters for the solution, reply with ONE short question about
   the most important missing fact — one or two sentences, a friendly acknowledgement at most, no advice, no
   rights, no steps, no {more_marker} marker, no {offer_marker} marker. A reply with a question never also gives the
   solution, not even «in case»: the solution comes in a later reply. Do not ask what is already in the
   conversation, the case context or the attached files. Usually 1–3 questions are enough; never more than four.
   Ask only what changes the solution: never where to file or which body to choose (you decide that), never the
   person's own name, address or ID number (the form asks them before payment). The other side's name and address
   are asked when the case does not hold them yet (facts_missing): the document needs its addressee (R-29).
   No questions first: when life or health is in danger right now (the emergency number comes first); when a short
   time limit may run out (say so in the first line, then ask); and for a general question about the law that is
   not the person's own dispute («сколько дней на возврат товара?») — answer it at once.
1-1. Documents first (owner 02.10): in the first reply after the gist is clear, ask for the documents in one
   sentence, together with the one question if there is one — what is in them you take yourself, it is never asked:
   «Пришлите фото чека и гарантийного талона — я сам возьму из них даты и суммы». Name the documents of this case:
   the case context lists them (documents_to_ask); without that list, the obvious ones for the subject — a receipt
   or contract, a warranty card, an act, photos, screenshots, the correspondence, a notice or a decision. Ask once;
   if the person has none or will send them later, go on with the questions. Facts in the attached files and in
   facts_known are never asked again; facts_missing are the facts still to learn before the solution.
1-2. The route (owner 02.10, R-31): when the case context holds «route», the solution IS that route — its steps, in
   its order, to its addressees; the server writes the steps from it. Explain those steps in the details (why, the
   norm, what to attach); never another first step, never «сразу в суд» when the route starts with a claim.
2. Once the facts are clear, give ONE solution — the best path by law for this person. Never «you can do A or B»,
   never a list of alternatives; mention another path only inside the details if the first one fails.
3. The short part is only (no greeting or introduction before it): a line «Что делать:» (in the reply language) and the steps «1.», «2.», «3.» — one short
   line each, at most 5 lines in all. Why, the rules, deadlines, documents to prepare and risks go only after the
   {more_marker} marker. No closing question after a solution: no «Хотите…?», «Есть ли у вас…?» — if a fact is
   still missing, ask it before the solution, never after it.
4. After a solution the app shows the buttons «Составить документ», «Дело под ключ» and «Нанять юриста»: do not
   describe them or sell them in the text; when a document is the next step, end with {offer_marker} as above.
5. Practical, the shortest real path (owner 02.10): build the steps on what the person already has — their own
   estimate of the loss, the act, photos, receipts, the correspondence — and never send them to gather more unless
   the law requires it for this step. No independent appraisal, notary, expert or extra certificate «just in
   case»: if the other side disputes the amount, that is decided later (in court the judge may order an
   appraisal). The first step is the one that gets money or a decision soonest: usually our document to the other
   side with the person's own sum, then — if refused or silent — the body or court. Name what it costs and how long
   it takes only when it matters for the choice."""


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


MORE_MARKER = "[[MORE]]"  # between the short answer and the details; the app shows the details under «Подробнее»
_MORE = re.compile(r"\[\[\s*MORE\s*\]\]", re.IGNORECASE)

# Added to the tool results when the person already reads part of the reply: the model continues, it does not start
# over (open models wrote the whole answer again after a tool call: a doubled reply, 30.09).
CONTINUE_NOTE = ("The person already sees what you wrote above in this reply. Continue right after it: do not repeat "
                 "the short answer or anything already written. Write the " + MORE_MARKER + " marker only if you have "
                 "not written it yet. Do not announce another look-up; just write the rest.")
# P0 01.10 (an answer cut mid-word «…если оплата была бе»): a round that stops before the end of its text — the token
# limit, a safety/recitation/other stop, a stream that ended without a finish reason or broke — is continued from
# where it stopped, at most this many times; a reply still cut then ends at its last whole sentence.
MAX_CONTINUE = 2
CUT_STOPS = ("max_tokens", "cut", "error")
CUT_NOTE = ("Your reply above was cut off before its end. Continue it exactly where it stopped — in the middle of the "
            "word or the sentence if it stopped there — without repeating anything already written and without "
            "starting over, then finish the reply in the reply shape asked for.")
SEAM_NOTE = (" It stopped at «{word}»: begin with that word written again in full (completed if it was cut), then go "
             "on.")
TOOLS_OVER ="No more look-ups are possible in this reply: answer from what you already have."
# Added when the model has used up its tool rounds: the answer is written now.
FINAL_NOTE = ("No more tool calls are possible in this reply. Write the answer to the person now from what you "
              "already have, in the reply shape asked for.")

# A note a model writes just before a tool call ("Сейчас уточняю официальные источники…"): useful while the person
# waits, but the stored reply must not keep it hanging in the middle or at the end.
_FILLER = re.compile(
    r"\b(?:секунду|минутку|одну минуту|let me|one moment|just a moment|bir saniye|bir dakika)\b|"
    r"уточняю|уточню|проверю|проверяю|посмотрю|смотрю|поищу|ищу|найду|открою|открываю|загляну|сверю|сверяю|"
    r"тексеремін|тексерейін|қараймын|қарап шығайын|анықтаймын|іздеймін|"
    r"i'?ll check|i will check|i'?m checking|checking|looking (?:it )?up|i'?ll look|"
    r"kontrol ediyorum|kontrol edeyim|bakıyorum|bakayım|araştırıyorum|"
    r"لحظة|سأتحقق|أتحقق|دعني|سأبحث|أبحث", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?…:])[*_»\"')\]]*\s+")  # also after closing bold or quotes


def trailing_filler(text: str) -> str:
    """The look-up note at the end of a round that ended in a tool call ('' if the round ends with real content):
    the trailing sentences of its last paragraph that announce a look-up."""
    tail = re.split(r"\n|\[\[\s*MORE\s*\]\]", text.rstrip(), flags=re.IGNORECASE)[-1]
    sentences = [x for x in _SENTENCE_END.split(tail.strip()) if x.strip()]
    drop: list[str] = []
    while sentences and len(sentences[-1]) <= 160 and _FILLER.search(sentences[-1]):
        drop.insert(0, sentences.pop())
    if not drop:
        return ""
    # the exact end of the text that holds those sentences
    first = drop[0]
    at = text.rstrip().rfind(first)
    return text.rstrip()[at:] if at >= 0 else ""


_WHOLE_END = re.compile(r"[.!?…][*_»\"')\]]*(?=\s|$)|\n")


def whole_sentences(text: str) -> str:
    """The text up to the end of its last complete sentence or line (a reply still cut after its continuations)."""
    for m in reversed(list(_WHOLE_END.finditer(text))):
        line = text[text.rfind("\n", 0, m.start()) + 1:m.end()].strip()
        if re.fullmatch(r"\d+[.)]", line):
            continue  # «1.» opens a step, it does not end a sentence
        out = re.sub(r"\s*\[\[\s*MORE\s*\]\]\s*$", "", text[:m.end()].rstrip())
        if has_words(out):
            return out
    return text


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def _repeats(new: str, shown: str) -> bool:
    """``new`` says again what ``shown`` already said (mostly the same words)."""
    a, b = _words(new), _words(shown)
    if min(len(a), len(b)) < 4:
        return bool(new.strip()) and new.strip() == shown.strip()
    return len(a & b) / min(len(a), len(b)) >= 0.6


class RepeatGuard:
    """The text of a round after a tool call, when the person already reads part of the reply. Held back until it
    is clear whether the model starts over (writes the short answer again, a second [[MORE]]); the repeated part is
    dropped, the rest passes. The details are hidden under «Подробнее» anyway, so the short hold costs nothing."""

    HOLD = 600  # characters: a repeated short answer (≤ ~50 words) is shorter than this

    def __init__(self, shown: str):
        self.shown, self.buf, self.done = shown, "", False
        m = _MORE.search(shown)
        self.short = shown[:m.start()] if m else shown  # what the person sees as the short answer
        self.has_more = m is not None

    def feed(self, chunk: str) -> str:
        if self.done:
            return chunk
        self.buf += chunk
        m = _MORE.search(self.buf)
        if m or len(self.buf) >= self.HOLD:
            return self._decide(m, final=False)
        return ""

    def flush(self) -> str:
        return "" if self.done else self._decide(_MORE.search(self.buf), final=True)

    def _decide(self, m: re.Match[str] | None, final: bool) -> str:
        self.done = True
        buf = self.buf
        if m:
            head, tail = buf[:m.start()], buf[m.end():]
            if self.has_more:  # a second marker: what precedes it is the short answer again (or keep new words)
                return tail.lstrip() if not head.strip() or _repeats(head, self.short) else head + tail
            if head.strip() and _repeats(head, self.short):  # short answer again, first marker: keep the marker
                return MORE_MARKER + "\n" + tail.lstrip()
            return buf
        # no marker: drop leading paragraphs that say again what was shown (the last one only once it is complete)
        paras = re.split(r"(\n\s*\n)", buf.lstrip())
        shown_paras = [p for p in re.split(r"\n\s*\n", self.shown) if p.strip()]
        dropped = False
        while paras and (len(paras) > 2 or final) and any(_repeats(paras[0], p) for p in shown_paras):
            paras, dropped = paras[2:], True
        return "".join(paras).lstrip() if dropped else buf


# Section labels the prompt names («SHORT ANSWER», «DETAILS») that a model sometimes writes out anyway, in any language.
_LABEL = re.compile(r"(?im)^\s*\**\s*(short answer|details|короткий ответ|краткий ответ|подробности|детали|қысқа жауап|"
                    r"толығырақ|kısa cevap|ayrıntılar|الإجابة المختصرة|التفاصيل)\s*\**\s*[:：]\s*\**\s*")


def strip_labels(text: str) -> str:
    """The reply without written-out section labels («КОРОТКИЙ ОТВЕТ: …»)."""
    return _LABEL.sub("", text)


# owner 02.10 (flood case on 592f836: «2. Оцените ущерб. Пригласите оценщика…» despite rule 5): the free models do not
# always keep the prompt, so the reply is cleaned in code. A line that sends the person for an appraisal, an expert
# or a notary «just in case» is dropped and the steps are renumbered; «the court may order an appraisal» stays.
_EXTRA = re.compile(
    r"(?:пригласи|закаж|вызов|обрати\w*\s+к|проведи|получи|сдела|оплат)\w*\s[^\n]{0,60}?"
    r"(?:оценщик|независим\w*\s+(?:оценк|экспертиз)|экспертиз|нотариус|нотариальн)|"
    r"^\W*\d*[.)]?\s*\**\s*оцените\s+ущерб|"
    r"(?:бағалаушы|тәуелсіз\s+бағала|нотариус)|"
    r"(?:hire|order|get)\s[^\n]{0,40}?(?:apprais|expert\s+(?:report|opinion)|notar)",
    re.IGNORECASE | re.MULTILINE)
# Kept although they name an expert or an appraiser (ZANN 02.10, checked on adilet): the court orders an expertise on a
# party's motion or of its own accord (Civil Procedure Code art. 82 p. 3) — «суд назначит», «ходатайство об экспертизе»;
# and under compulsory motor insurance the victim may hire an appraiser at the insurer's expense when the insurer has
# not assessed the damage in time (Law on OGPO VTS art. 22 p. 3-1) — «за счёт страховщика».
_LAWFUL_EXTRA = re.compile(r"суд\w*[^\n]{0,40}назнач|назнач\w*[^\n]{0,40}суд|ходатайств|за\s+сч[её]т\s+страхов",
                           re.IGNORECASE)
_STEP = re.compile(r"^(\s*\**\s*)(\d+)([.)])", re.MULTILINE)


def drop_extra_steps(text: str) -> str:
    """The reply without lines that send the person to gather more (an appraiser, an expert, a notary); the
    numbered steps renumbered 1, 2, 3 in each block."""
    lines = text.split("\n")
    kept = [ln for ln in lines if not _EXTRA.search(ln) or _LAWFUL_EXTRA.search(ln)]
    if len(kept) == len(lines):
        return text
    out, n = [], 0
    for ln in kept:
        m = _STEP.match(ln)
        if m:
            n += 1
            ln = f"{m.group(1)}{n}{m.group(3)}{ln[m.end():]}"
        elif _MORE.search(ln):
            n = 0
        out.append(ln)
    return "\n".join(out)


def take_offer(text: str) -> tuple[str, bool]:
    """The reply without the document marker, and whether it had one (models sometimes drop a bracket)."""
    cleaned = re.sub(r"\[?\[\s*DOCUMENT\s*\]\]?", "", text)
    return cleaned.strip(), cleaned != text


# Some open models slip a word of Chinese or Japanese into an answer in a Cyrillic language ("если 母亲 работала"). The
# person never reads those scripts here, so such runs are dropped from the stream.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]+ ?")


def strip_foreign_script(text: str, language: str) -> str:
    if not text or language.lower().startswith(("chinese", "japanese", "korean", "中", "日", "한")):
        return text
    return _CJK.sub("", text)


# Owner 02.10 / ZANN: the chat model states deadlines and article numbers from memory (QA run: «10 рабочих дней» for the
# motor insurer, the law says 5; «ст. 157 — приостановить работу», a Russian rule). A term of days or an article number
# reaches the person only if it is checked: in the country rules (packs/<cc>/pack.yaml chat_rules, checked on
# adilet) or in an article opened in this reply. Anything else is taken out before the reply is stored and sent.
_RULE_DAYS = re.compile(r"(\d+)\s*(calendar|working|business|banking)?\s*days?\b", re.IGNORECASE)
_RULE_ARTS = re.compile(r"\barts?\.\s*((?:\d+(?:-\d+)?(?:\s*p\.\s*\d+(?:-\d+)?)?(?:,\s*|\s+and\s+)?)+)", re.IGNORECASE)
_TERM = re.compile(
    r"(?:\s*(?:в\s+течение|через|за|не\s+позднее|не\s+позже|до|в\s+срок\s+до|в\s+срок)\s+)?"
    r"(\d+)(?:-?(?:х|и|ти|ми|ть|ух|ёх|ех))?\s*(?:\(\w+\)\s*)?(календарн\w*|рабоч\w*|банковск\w*)?\s*"
    r"(?:дн(?:я|ей|ю|ям|ями)\b|день\b|сут(?:ок|ки)\b)", re.IGNORECASE)
_ART = re.compile(r"(\(\s*)?(?:(стать[яеиюй]\w*)|ст\.)\s*(\d+(?:-\d+)?)((?:\s*(?:,|и)?\s*(?:п(?:ункт\w*|п?\.)|ч(?:аст\w*|\.)|подпункт\w*)\s*\d+(?:-\d+)?\)?)*)(\s*\))?",
                  re.IGNORECASE)
_ART_PAREN = re.compile(r"\s*\((?=[^()]*(?:стать\w*|ст\.)\s*\d)[^()]*\)", re.IGNORECASE)
_NORM_WORD = {"статья": "норма", "статье": "норме", "статьи": "нормы", "статью": "норму", "статьей": "нормой",
              "статьёй": "нормой"}
_STEP_LINE = re.compile(r"^\s*(?:\d+[.)]|[-•*]|\*\*)")


_NEGATED = re.compile(r"«[^»]*$|\"[^\"\n]*$")  # inside a quoted wrong example: «3 days», "7 days to return"


# months and years: checked only where the reply states a time limit («в течение двух месяцев», «срок — один год»,
# «есть один месяц на …»), never in the person's own facts («ноутбук держат уже два месяца»)
_RULE_MONTHS = re.compile(r"\b(\d+|one|two|three|six)\s*(months?|years?)\b", re.IGNORECASE)
_WORD_N = {"one": 1, "two": 2, "three": 3, "six": 6, "один": 1, "одного": 1, "одним": 1, "два": 2, "двух": 2,
           "три": 3, "трёх": 3, "трех": 3, "шесть": 6, "шести": 6}
_TERM_MONTHS = re.compile(
    r"(?:в\s+течение|через|не\s+позднее|не\s+позже|срок\w*[^.\n]{0,25}?|есть|остаётся|остается|да[её]тся|"
    r"составляет)\s+(\d+|один|одного|одним|два|двух|три|трёх|трех|шесть|шести)\s*(месяц\w*|год\w*|лет)\b",
    re.IGNORECASE)


def _months(n: str, unit: str) -> tuple[int, str]:
    num = int(n) if n.isdigit() else _WORD_N.get(n.lower(), -1)
    return num, "year" if unit.lower().startswith(("year", "год", "лет")) else "month"


def _kind(word: str | None) -> str:
    w = (word or "").lower()
    return "working" if w.startswith(("working", "business", "рабоч", "banking", "банков")) else \
        "calendar" if w.startswith(("calendar", "календар")) else ""


def checked_terms(rules: str) -> tuple[set[tuple[int, str]], set[str]]:
    """Terms of days and article numbers the country rules state as checked; a number in a «never …», «no …» or a
    quoted wrong example («3 days», «7 days to return») is not one of them."""
    rules = rules or ""
    days = {(int(m.group(1)), _kind(m.group(2))) for m in _RULE_DAYS.finditer(rules)
            if not _NEGATED.search(rules[:m.start()])}
    arts: set[str] = set()
    for m in _RULE_ARTS.finditer(rules):
        group = re.sub(r"p\.\s*\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?(?=[^\d-]|$))*", "", m.group(1))
        arts |= set(re.findall(r"\b(\d+(?:-\d+)?)\b", group))
    return days, arts


def keep_checked(text: str, rules: str, opened: set[str], opened_any: bool = False) -> tuple[str, list[str]]:
    """The reply without terms of days and article numbers that nobody checked; returns what was taken out."""
    days, arts = checked_terms(rules)
    arts |= set(opened)
    months = {_months(m.group(1), m.group(2)) for m in _RULE_MONTHS.finditer(rules or "")
              if not _NEGATED.search((rules or "")[:m.start()])}
    removed: list[str] = []

    def ok(m: re.Match) -> bool:  # «10 рабочих дней» is not «10 calendar days»; «10 дней» may be either
        n, kind = int(m.group(1)), _kind(m.group(2))
        return (n, kind) in days if kind else any(d == n for d, _ in days)

    def art(m: re.Match) -> str:
        if m.group(3) in arts:
            return m.group(0)
        removed.append(m.group(0).strip())
        if m.group(1) or m.group(5):  # «(ст. 157 ТК)» → nothing
            return ""
        word = (m.group(2) or "").lower()
        return _NORM_WORD.get(word, "нормы") + ("" if m.group(0).endswith(" ") else "")

    def paren(m: re.Match) -> str:
        nums = re.findall(r"(?:стать\w*|ст\.)\s*(\d+(?:-\d+)?)", m.group(0), re.IGNORECASE)
        if all(n in arts for n in nums):
            return m.group(0)
        removed.append(m.group(0).strip())
        return ""

    out = []
    for line in text.split("\n"):
        if not opened_any:
            bad = [m for m in _TERM.finditer(line) if not ok(m)]
            bad += [m for m in _TERM_MONTHS.finditer(line) if _months(m.group(1), m.group(2)) not in months]
            bad.sort(key=lambda m: m.start())
            if bad:
                if _STEP_LINE.match(line):
                    for m in reversed(bad):
                        removed.append(m.group(0).strip())
                        line = line[:m.start()] + line[m.end():]
                else:
                    parts = re.split(r"(?<=[.!?])\s+", line)
                    keep = [p for p in parts if all(ok(m) for m in _TERM.finditer(p))
                            and all(_months(m.group(1), m.group(2)) in months for m in _TERM_MONTHS.finditer(p))]
                    removed += [p for p in parts if p not in keep]
                    line = " ".join(keep)
        line = _ART_PAREN.sub(paren, line)  # «(статья 53 Трудового кодекса)» goes whole, never half
        line = _ART.sub(art, line)
        line = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"[ \t]{2,}", " ", line)).rstrip()
        out.append(line)
    return "\n".join(out), removed


def mentioned_articles(text: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in ARTICLE_MENTION.finditer(text)}


class ChatAgent:
    def __init__(self, client: Any, model: str, adilet: Adilet | None = None, *,
                 portal_domain: str = "adilet.zan.kz", max_turns: int = 6, max_tokens: int = 2000,
                 web_search: bool = True, library: Any = None):
        self.client, self.model, self.max_turns, self.max_tokens = client, model, max_turns, max_tokens
        self.portal_domain, self.web_search = portal_domain, web_search
        self.library = library  # konsilier.official.search.OfficialLibrary, or None
        # the portal tools are the legal agent's; the chat reuses them rather than re-implementing
        self._law = LawAgent(client, model, adilet or Adilet(), portal_domain=portal_domain)

    def tools(self, use_portal: bool, use_library: bool = False) -> list[dict[str, Any]]:
        out = []
        if use_library:
            out.append({"name": "official_sources",
                        "description": "Search the library of official state pages (services, benefits, grants, "
                                       "business support, tenders, e-government how-tos). Returns excerpts with the "
                                       "page URL, title and domain.",
                        "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                                         "properties": {"query": {"type": "string", "description":
                                                                  "A few key words in the language of the pages"}}}})
        for t in self._law.tools():
            if t.get("name") == "web_search":
                if use_portal and self.web_search:  # basic search variant: works on the fast model too
                    out.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 2,
                                "allowed_domains": [self.portal_domain]})
            elif t["name"] in ("act_contents", "get_article"):
                if use_portal:
                    out.append(t)
            else:
                out.append(t)
        return out

    def stream(self, history: list[dict[str, str]], *, context: dict[str, Any], language: str, country: str,
               use_portal: bool) -> Iterator[dict[str, Any]]:
        """Yield {"type": "text", "text"} chunks and {"type": "tool", "name"} markers; the last event is
        {"type": "done", "result": ChatResult}."""
        t0 = time.perf_counter()
        timing: dict[str, Any] = {"rounds": [], "tools": []}
        case_id = context.get("case_id", "")
        got: dict[tuple[str, str], Any] = {}
        found: dict[str, Hit] = {}  # official pages seen in this turn, by URL
        case_note = json.dumps(context.get("case", {}), ensure_ascii=False)
        messages: list[dict[str, Any]] = [{"role": m["role"], "content": m["text"]} for m in history[-HISTORY_TURNS:]]
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]
        cc, lang = getattr(context.get("pack"), "country", None), context.get("lang")
        use_library = self.library is not None and self.library.available(cc)
        search = " or with web_search on the official portal" if self.web_search else ""
        system = (SYSTEM + PAID_DOCUMENT_RULE + FACTS_FIRST_RULE).format(country=country, language=language, offer_marker=OFFER_MARKER, more_marker=MORE_MARKER,
                               portal_rule=PORTAL_RULE.format(search=search) if use_portal else NO_PORTAL_RULE,
                               official_rule=OFFICIAL_RULE if use_library else NO_OFFICIAL_RULE)
        rules = getattr(getattr(context.get("pack"), "manifest", None), "chat_rules", "")
        if rules:  # the country's own rules for the chat (packs/<cc>/pack.yaml chat_rules)
            system += "\n\nCountry rules:\n" + rules.strip()
        if use_portal and context.get("key_acts"):
            system += "\n\nMain acts on the official portal (code — title):\n" + "\n".join(
                f"{a['code']} — {a['title']}" for a in context["key_acts"])
        if use_library:
            portals = self.library.portals(cc, lang or "")
            if portals:
                system += "\n\nOfficial portals (domain — what is there):\n" + "\n".join(
                    f"{p['domain']} — {p['name']}: {p['about']}" for p in portals)
            # pre-retrieval: every model gets the best excerpts, also one that never calls tools
            last = next((m["text"] for m in reversed(history) if m["role"] == "user"), "")
            t = time.perf_counter()
            hits = self._library_search(last, cc, lang, PRE_HITS, found)
            timing["library_ms"] = _ms(t)
            log.info("chat timing: case=%s phase=library ms=%d hits=%d", case_id, timing["library_ms"], len(hits))
            system += ("\n\nOfficial library excerpts for the last message (may be off-topic; cite what you use):\n"
                       + json.dumps(hits, ensure_ascii=False) if hits else
                       "\n\nThe official library found nothing for the last message as written; if it is about a "
                       "state service, try official_sources with other key words.")
        system += "\n\nCase context (names and numbers are replaced by placeholders):\n" + case_note
        tools = self.tools(use_portal, use_library)
        # the prompt's size drives the model's time to the first token (about 4 characters a token)
        timing["system_chars"] = len(system)
        timing["prompt_chars"] = len(system) + len(json.dumps(tools, ensure_ascii=False)) + sum(
            len(m["content"]) for m in messages if isinstance(m["content"], str))
        timing["setup_ms"] = _ms(t0)
        usage = {"input_tokens": 0, "output_tokens": 0}
        reply = ""  # what the person was sent in this reply
        fillers: list[tuple[int, int]] = []  # look-up notes shown before a tool call: (start, end) in ``reply``
        calls = 0
        served = ""  # the provider of a chain that answered keeps the rest of the turn (its own tool calls)
        tool_rounds = 0
        cuts: list[str] = []  # rounds that stopped before the end of their text: "provider:reason" (P0 01.10)
        cut_open = False  # the last round was cut and nothing has completed it yet
        next_seam: str | None = None  # the word a cut round stopped at: its continuation writes it again first
        n = -1
        # up to max_turns rounds with tools; a turn that still ends in a tool call gets one more round to write;
        # a round cut before its end (token limit, safety stop, dropped stream) is continued up to MAX_CONTINUE times
        while True:
            n += 1
            last_round = tool_rounds >= self.max_turns  # tools are no longer run: the answer is written now
            t_round = time.perf_counter()
            first_ms = None
            round_text = ""  # what this round added to the reply (after the repeat guard)
            raw_text = ""  # what the model wrote in this round
            final: Any = None
            error = ""
            s: Any = None
            seam, held, next_seam = next_seam, "", None
            round_seam = seam
            # after a tool call with part of the reply already shown: the model must continue, not start over
            guard = RepeatGuard(reply) if n and reply.strip() else None
            kw: dict[str, Any] = {"prefer": served} if served and getattr(self.client, "accepts_prefer", False) else {}
            try:
                with self.client.messages.stream(model=self.model, max_tokens=self.max_tokens, system=system,
                                                 tools=tools, messages=messages, **kw) as s:
                    chunks = iter(s.text_stream)
                    while True:
                        raw = next(chunks, None)
                        if raw is not None:
                            raw = strip_foreign_script(raw, language)
                            raw_text += raw
                        if seam is not None:  # a continuation repeats the cut word first: it is written once
                            held += raw or ""
                            if raw is not None and len(held) <= len(seam):
                                continue
                            text_in = held[len(seam):] if held.startswith(seam) else held
                            seam = None
                        else:
                            text_in = raw or ""
                        out = guard.feed(text_in) if guard and text_in else text_in
                        if raw is None:
                            final = s.get_final_message()
                            out += guard.flush() if guard else ""
                        if out and (reply.strip() or out.strip()):  # never open a reply with blank lines
                            if first_ms is None:
                                first_ms = _ms(t_round)
                                if "ttft_ms" not in timing:
                                    timing["ttft_ms"] = _ms(t0)
                                    log.info("chat timing: case=%s phase=first_token ms=%d round=%d", case_id,
                                             timing["ttft_ms"], n + 1)
                            reply += out
                            round_text += out
                            yield {"type": "text", "text": out}
                        if raw is None:
                            break
            except Exception as e:
                if not reply.strip():
                    raise  # nothing shown yet: the caller tries the fallback or says «busy», as before
                # the stream broke after the person started reading (a dropped connection, every provider failed
                # on a continuation): never leave the answer cut there — continue it below, else end it cleanly
                error = f"{type(e).__name__}: {str(e)[:120]}"
                log.warning("chat round %d broke after %d characters: %s", n + 1, len(round_text), error)
            provider = getattr(s, "provider", "") or getattr(self.client, "name", "")
            if final is not None:
                served = getattr(s, "provider", "") or served
            stop = final.stop_reason if final is not None else "error"
            finish = getattr(final, "finish", "") or ""
            rnd: dict[str, Any] = {"n": n + 1, "provider": provider, "first_ms": first_ms, "ms": _ms(t_round),
                                   "stop": stop}
            if finish:
                rnd["finish"] = finish
            if error:
                rnd["error"] = error
            if attempts := getattr(s, "attempts", None):
                rnd["attempts"] = attempts
            timing["rounds"].append(rnd)
            log.info("chat timing: case=%s phase=round %s", case_id, json.dumps(rnd, ensure_ascii=False))
            if final is not None:
                usage["input_tokens"] += final.usage.input_tokens
                usage["output_tokens"] += final.usage.output_tokens
                searches = getattr(getattr(final.usage, "server_tool_use", None), "web_search_requests", 0) or 0
                if searches:  # Claude's server web search is billed per search
                    usage["web_search_requests"] = usage.get("web_search_requests", 0) + int(searches)
            if stop in CUT_STOPS or (last_round and stop == "tool_use"):
                cuts.append(f"{provider}:{finish or stop}")
                cut_open = True
                log.warning("chat=truncated case=%s round=%d reason=%s chars=%d", case_id, n + 1, cuts[-1],
                            len(round_text))
                if len(cuts) > MAX_CONTINUE:
                    break  # still cut: the reply is ended at its last whole sentence below
                if stop == "tool_use":  # tools are over: the calls are answered with «not possible», then write
                    messages.append({"role": "assistant", "content": final.content})
                    results = [{"type": "tool_result", "tool_use_id": b.id, "content": TOOLS_OVER}
                               for b in final.content if b.type == "tool_use"]
                    results.append({"type": "text", "text": FINAL_NOTE})
                    if reply.strip():
                        results.append({"type": "text", "text": CONTINUE_NOTE})
                    messages.append({"role": "user", "content": results})
                    if reply.strip() and not reply.endswith("\n"):
                        reply += "\n\n"
                        yield {"type": "text", "text": "\n\n"}
                elif raw_text.strip():  # the model's own words so far, and «continue exactly there»
                    messages.append({"role": "assistant", "content": [{"type": "text", "text": raw_text}]})
                    word = re.search(r"\w+$", reply)
                    next_seam = word.group(0) if word else None
                    messages.append({"role": "user", "content": CUT_NOTE + (
                        SEAM_NOTE.format(word=next_seam) if next_seam else "")})
                else:  # nothing written in this round: the same request once more
                    next_seam = round_seam
                continue
            if has_words(round_text) or stop == "tool_use":
                cut_open = False
            if last_round:  # the extra round: its words are the answer
                break
            messages.append({"role": "assistant", "content": final.content})
            if stop == "tool_use":
                tool_rounds += 1
                # a look-up note at the end of this round ("Сейчас уточняю…") is shown while the tool runs; the
                # stored reply drops it only if more words follow (never leaving the answer ending before it)
                if (filler := trailing_filler(round_text)) and reply.rstrip().endswith(filler):
                    fillers.append((len(reply.rstrip()) - len(filler), len(reply.rstrip())))
                results: list[dict[str, Any]] = []
                for b in final.content:
                    if b.type == "tool_use":
                        calls += 1
                        yield {"type": "tool", "name": b.name}
                        t_tool = time.perf_counter()
                        source = "code"
                        if b.name == "official_sources" and use_library:
                            hits = self._library_search(str(dict(b.input).get("query", "")), cc, lang, TOOL_HITS,
                                                        found)
                            content = (json.dumps(hits, ensure_ascii=False) if hits else
                                       "nothing found in the official library: say so and name the portal to check")
                            source = "library"
                        else:
                            content = self._law._run_tool(b.name, dict(b.input), context, got)
                            if b.name in ("get_article", "act_contents"):
                                source = self._law.adilet.last_source()
                        tool = {"name": b.name, "ms": _ms(t_tool), "source": source}
                        timing["tools"].append(tool)
                        log.info("chat timing: case=%s phase=tool %s", case_id, json.dumps(tool))
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
                if tool_rounds == self.max_turns:
                    results.append({"type": "text", "text": FINAL_NOTE})
                if reply.strip():
                    results.append({"type": "text", "text": CONTINUE_NOTE})
                messages.append({"role": "user", "content": results})
                if reply.strip() and not reply.endswith("\n"):  # the next words start a new paragraph
                    reply += "\n\n"
                    yield {"type": "text", "text": "\n\n"}
                continue
            if stop == "pause_turn" and tool_rounds + 1 < self.max_turns:
                tool_rounds += 1
                continue
            break
        for a, b in reversed(fillers):
            if has_words(take_offer(reply[b:])[0]):  # words follow the note: it is taken out
                reply = reply[:a].rstrip() + reply[b:]
        text = reply.strip()
        if cut_open:
            # still cut after the continuations: the stored reply ends at its last whole sentence, never mid-word
            text = whole_sentences(text)
            timing["trimmed"] = True
        if cuts:
            timing["truncated"] = cuts
            log.warning("chat=truncated case=%s reasons=%s repaired=%s", case_id, ",".join(cuts),
                        "trimmed" if cut_open else "continued")
        if not has_words(take_offer(text)[0]):  # blank or only a marker is no answer either
            # nothing to show (the model only called tools, or wrote nothing): a failure, never an empty reply —
            # the caller tries the fallback or tells the person to try again in a minute
            timing["total_ms"] = _ms(t0)
            log.warning("chat timing: case=%s empty reply %s", case_id, json.dumps(timing, ensure_ascii=False))
            raise EmptyReply("the model wrote no answer")
        result = self._check(text, got, calls, usage, rules)
        result.truncated = ",".join(cuts)
        result.trimmed = cut_open
        result.sources = [{"url": h.url, "title": h.title, "domain": h.domain} for h in found.values()
                          if h.url in text or h.domain in text]
        timing["total_ms"] = _ms(t0)
        timing["provider"] = served or getattr(self.client, "name", "")
        result.timing = timing
        yield {"type": "done", "result": result}

    def _library_search(self, query: str, cc: str | None, lang: str | None, limit: int,
                        found: dict[str, Hit]) -> list[dict[str, str]]:
        """Excerpts of the official library for the model; never raises (the chat goes on without them)."""
        if not query.strip() or not cc:
            return []
        try:
            hits = self.library.search(query[:500], cc, lang, limit)
        except Exception:
            log.exception("official library search failed")
            return []
        for h in hits:
            found.setdefault(h.url, h)
        return [{"url": h.url, "domain": h.domain, "title": h.title, "section": h.heading, "excerpt": h.snippet}
                for h in hits]

    @staticmethod
    def _check(text: str, got: dict[tuple[str, str], Any], calls: int, usage: dict[str, int],
               rules: str = "") -> ChatResult:
        read = {num: r for (_, num), r in got.items()}
        said = mentioned_articles(text)  # what the model wrote: the «unchecked» metric counts it before the cleaning
        text, removed = keep_checked(text, rules, set(read), opened_any=bool(read))
        if removed:
            log.warning("chat=unchecked_removed %s", json.dumps(removed, ensure_ascii=False)[:500])
        mentioned = mentioned_articles(text)
        norms = [{"act": r.act_title, "act_code": r.code, "article": r.number, "title": r.title, "url": r.url}
                 for num, r in read.items() if num in mentioned]
        text, offer = take_offer(drop_extra_steps(strip_labels(text)))
        return ChatResult(text, norms, unchecked=bool(said - set(read)), tool_calls=calls, usage=usage,
                          offer_document=offer)
