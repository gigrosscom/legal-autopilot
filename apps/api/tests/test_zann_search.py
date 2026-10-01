"""Zann search («ищет и цитирует»): splitting collected acts into articles, incremental indexing by sha256, the
hybrid search (direct references, words, optional vectors, RRF), GET /v1/zann/search and the chat's law_search —
without network and without a model (a fake embedder stands in for multilingual-e5)."""

from __future__ import annotations

import gzip
import hashlib
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from konsilier.chat import ChatAgent
from konsilier.core.adapters.storage import LocalStorage
from konsilier.core.db import make_engine, make_session_factory
from konsilier.core.models import Base, ZannAct, ZannArticle, ZannFile, ZannIndexed
from konsilier.lawagent.sources import Adilet
from konsilier.zann.embed import VectorTable, pack, unpack
from konsilier.zann.index import Indexer, ZannIndexJob, article_url, index_metrics, split_act
from konsilier.zann.search import LawIndex, references, search

from .test_chat import StreamingClient
from .test_lawagent import fake_fetch, tool_use

# Invented texts in the shape of adilet acts (codes are real, wording is not the law): fixtures only.
TK = "K1500000414"
TK_RU = """Трудовой кодекс Республики Казахстан
Глава 1. ОБЩИЕ ПОЛОЖЕНИЯ
Статья 1. Основные понятия, используемые в настоящем Кодексе
В настоящем Кодексе используются следующие основные понятия: работник, работодатель, трудовой договор.
Статья 22. Основные права и обязанности работника
Работник имеет право на своевременную и в полном объеме выплату заработной платы.
Глава 7. ПРЕКРАЩЕНИЕ ТРУДОВОГО ДОГОВОРА
Статья 113. Порядок выплаты при увольнении
При прекращении трудового договора выплата всех сумм, причитающихся работнику, производится не позднее трех
рабочих дней после его прекращения. Работодатель выплачивает компенсацию за неиспользованный отпуск.
Статья 113-1. Удержания из заработной платы
Удержания из заработной платы работника производятся по письменному согласию.
"""
TK_KK = """Қазақстан Республикасының Еңбек кодексі
113-бап. Жұмыстан босатылған кезде төлеу тәртібі
Еңбек шарты тоқтатылған кезде қызметкерге тиесілі барлық сомалар үш жұмыс күнінен кешіктірілмей төленеді.
"""
ZPP = "Z100000274_"
ZPP_RU = """О защите прав потребителей
Статья 9. Право потребителя на возврат товара
Потребитель вправе вернуть товар надлежащего качества в течение четырнадцати календарных дней.
Статья 30. Требования потребителя при обнаружении недостатков товара
Потребитель вправе потребовать замены товара с недостатками или возврата уплаченной суммы.
"""
POST = "P2400000123"
POST_RU = ("Об утверждении Правил выплаты пособий\n\n"
           "1. Утвердить прилагаемые Правила выплаты социальных пособий по уходу за ребенком.\n\n"
           "2. Настоящее постановление вводится в действие по истечении десяти календарных дней.\n")
OLD = "Z000000001_"
OLD_RU = "О труде\nСтатья 113. Выплата при увольнении\nВыплата при увольнении производится в день увольнения работника.\n"

ACTS = [(TK, "КОД", "upd", {"ru": ("Трудовой кодекс Республики Казахстан", TK_RU),
                             "kk": ("Қазақстан Республикасының Еңбек кодексі", TK_KK)}),
        (ZPP, "ЗАК", "upd", {"ru": ("О защите прав потребителей", ZPP_RU)}),
        (POST, "ПОСТ", "new", {"ru": ("Об утверждении Правил выплаты пособий", POST_RU)}),
        (OLD, "ЗАК", "yts", {"ru": ("О труде", OLD_RU)})]


def put_file(s, storage, code, lang, title, text, act_type="ЗАК", status="upd"):
    data = gzip.compress(text.encode())
    key = f"zann/corpus/{code}.{lang}.txt.gz"
    storage.put(key, data, "application/gzip")
    act = s.get(ZannAct, code) or ZannAct(code=code, title=title, act_type=act_type, status=status, state="done")
    act.status = status
    s.merge(act)
    f = s.get(ZannFile, (code, lang)) or ZannFile(code=code, lang=lang)
    f.key, f.url, f.title = key, f"https://old.adilet.zan.kz/{'kaz' if lang == 'kk' else 'rus'}/docs/{code}", title
    f.sha256, f.chars, f.bytes = hashlib.sha256(text.encode()).hexdigest(), len(text), len(data)
    f.changed_at = datetime.now(timezone.utc)
    s.merge(f)
    s.commit()


@pytest.fixture
def db(tmp_path):
    engine = make_engine(os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/zann.db")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def corpus(db, tmp_path):
    storage = LocalStorage(tmp_path / "files")
    with db() as s:
        for code, va, st, langs in ACTS:
            for lang, (title, text) in langs.items():
                put_file(s, storage, code, lang, title, text, va, st)
    return db, storage


class FakeEmbedder:
    """Bag of a few key words → a normalised vector: enough to test fusion without a model."""

    name, dim = "fake", 4
    WORDS = (("увол", "босат"), ("потребит", "товар"), ("пособ", "ребен"), ("удерж",))

    def _vec(self, text):
        low = text.lower()
        v = [float(sum(low.count(w) for w in ws)) for ws in self.WORDS]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def passages(self, texts):
        return [self._vec(t) for t in texts]

    def query(self, text):
        return self._vec(text)


# ------------------------------------------------------------------ splitting
def test_split_act_reuses_article_headings_and_cuts_acts_without_articles():
    chunks = split_act(TK_RU)
    assert [(c.number, c.heading) for c in chunks] == [
        ("1", "Основные понятия, используемые в настоящем Кодексе"), ("22", "Основные права и обязанности работника"),
        ("113", "Порядок выплаты при увольнении"), ("113-1", "Удержания из заработной платы")]
    assert "трех\nрабочих дней" in chunks[2].text and "Глава 7" not in chunks[1].text  # a chapter ends an article
    kk = split_act(TK_KK)
    assert [(c.number, c.heading) for c in kk] == [("113", "Жұмыстан босатылған кезде төлеу тәртібі")]
    pieces = split_act(POST_RU)
    assert len(pieces) == 1 and pieces[0].number == "" and "пособий" in pieces[0].heading
    long = "Статья 5. Длинная\n" + ("Очень длинный абзац статьи. " * 60 + "\n") * 30
    parts = split_act(long)
    assert len(parts) > 1 and {p.number for p in parts} == {"5"} and parts[1].heading == "Длинная (ч. 2)"
    assert all(len(p.text) <= 30000 for p in parts)


def test_article_url_scrolls_to_the_article():
    assert article_url(TK, "ru", "113") == (
        "https://old.adilet.zan.kz/rus/docs/K1500000414#:~:text=%D0%A1%D1%82%D0%B0%D1%82%D1%8C%D1%8F%20113.")
    assert article_url(TK, "kk", "113").startswith("https://old.adilet.zan.kz/kaz/docs/K1500000414#:~:text=113-")
    assert article_url(POST, "ru", "") == "https://old.adilet.zan.kz/rus/docs/P2400000123"


# ------------------------------------------------------------------ incremental indexing
def test_index_is_incremental_by_sha256_and_status(corpus):
    db, storage = corpus
    stats = Indexer(db, storage).run()
    assert (stats.files, stats.articles, stats.stopped) == (5, 9, "idle")
    with db() as s:
        tk113 = s.query(ZannArticle).filter_by(code=TK, lang="ru", number="113").one()
        assert tk113.act_title == "Трудовой кодекс Республики Казахстан" and tk113.act_type == "КОД"
        assert tk113.url.startswith("https://old.adilet.zan.kz/rus/docs/K1500000414#:~:text=")
        assert index_metrics(s)["articles"] == 9
    again = Indexer(db, storage).run()
    assert (again.files, again.articles) == (0, 0)  # nothing changed: one query
    with db() as s:  # a new wording of one file, a status change of another, one file gone
        put_file(s, storage, ZPP, "ru", "О защите прав потребителей",
                 ZPP_RU + "Статья 31. Сроки\nТребования удовлетворяются в течение десяти дней.\n")
        s.get(ZannAct, POST).status = "yts"
        s.delete(s.get(ZannFile, (TK, "kk")))
        s.commit()
    third = Indexer(db, storage).run()
    assert (third.files, third.removed) == (2, 1)
    with db() as s:
        assert s.query(ZannArticle).filter_by(code=ZPP).count() == 3
        assert s.query(ZannArticle).filter_by(code=POST).one().status == "yts"
        assert s.query(ZannArticle).filter_by(code=TK, lang="kk").count() == 0
        assert s.get(ZannIndexed, (TK, "kk")) is None


def test_index_respects_limit_and_budget_and_survives_a_missing_file(corpus):
    db, storage = corpus
    assert Indexer(db, storage).run(limit=2).stopped == "limit"
    with db() as s:
        s.get(ZannFile, (ZPP, "ru")).key = "zann/corpus/missing.txt.gz"
        s.commit()
    ticks = iter([0, 0] + [1000] * 100)
    stats = Indexer(db, storage, clock=lambda: next(ticks)).run(budget_seconds=10)
    assert stats.stopped == "budget"
    stats = Indexer(db, storage).run()
    assert stats.errors == 1 and stats.stopped == "idle"


def test_index_job_runs_in_the_background_on_schedule_and_on_kick(corpus):
    db, storage = corpus
    started = []
    job = ZannIndexJob(lambda: Indexer(db, storage), every_minutes=30, start=lambda fn: (started.append(1), fn()))
    now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
    job(None, now)
    assert job.last.files == 5 and len(started) == 1
    job(None, now.replace(minute=10))
    assert len(started) == 1  # not yet
    job.kick()  # a corpus run ended
    job(None, now.replace(minute=11))
    assert len(started) == 2 and job.last.files == 0


# ------------------------------------------------------------------ search
def test_references_are_parsed():
    assert references("что говорит ст. 113 ТК РК?") == [("113", ("трудовой кодекс",))]
    assert references("113-бап Еңбек кодексі") == [("113", ("еңбек кодексі",))]
    assert references("статья 9 Закона «О защите прав потребителей»")[0][0] == "9"
    assert references("статья 5 K1500000414") == [("5", ("K1500000414",))]
    assert references("уволили без расчёта") == []


def test_words_search_finds_and_cites_the_article(corpus):
    db, storage = corpus
    Indexer(db, storage).run()
    with db() as s:
        hits = search(s, "Уволили, не выплатили расчёт при увольнении")
        assert hits[0].code == TK and hits[0].number == "113" and hits[0].lang == "ru"
        assert hits[0].citation == "ст. 113, Трудовой кодекс Республики Казахстан"
        assert hits[0].url.startswith("https://old.adilet.zan.kz/rus/docs/K1500000414#:~:text=")
        assert "трех" in hits[0].snippet
        # the lost-force law with the same words ranks below the code in force
        codes = [h.code for h in hits]
        assert OLD in codes and codes.index(OLD) > codes.index(TK)
        kk = search(s, "жұмыстан босатылған кезде төлеу", lang="kk")
        assert kk[0].citation == "113-бап, Қазақстан Республикасының Еңбек кодексі"
        assert search(s, "вернуть товар надлежащего качества")[0].number == "9"
        assert search(s, "пособие по уходу за ребенком")[0].code == POST
        assert search(s, "и или на") == []


def test_direct_reference_comes_first(corpus):
    db, storage = corpus
    Indexer(db, storage).run()
    with db() as s:
        hits = search(s, "ст. 113 ТК")
        assert hits[0].match == "ref" and (hits[0].code, hits[0].number) == (TK, "113")
        hits = search(s, "статья 30 Закона о защите прав потребителей")
        assert (hits[0].code, hits[0].number, hits[0].match) == (ZPP, "30", "ref")


def test_hybrid_search_fuses_words_and_vectors(corpus):
    db, storage = corpus
    emb = FakeEmbedder()
    stats = Indexer(db, storage, embedder=emb).run()
    assert stats.embedded == 9
    index = LawIndex(db, emb, min_score=0)
    hits = index.search("меня выгнали с работы, увольнение без денег")
    assert hits[0].code in (TK, OLD) and hits[0].match in ("hybrid", "words", "semantic")
    assert any(h.match == "hybrid" for h in hits)
    # semantic alone finds what shares no word stem with the article
    sem = index.search("удержали")
    assert any(h.number == "113-1" for h in sem)


def test_vectors_pack_and_rank():
    v = [0.6, 0.8, 0.0]
    assert [round(x, 3) for x in unpack(pack(v))] == [0.6, 0.8, 0.0]
    t = VectorTable()
    t.load([(1, pack([1.0, 0.0])), (2, pack([0.0, 1.0])), (3, pack([0.7071, 0.7071]))])
    assert [i for i, _ in t.top([1.0, 0.0], 2)] == [1, 3]


def test_full_text_search_is_fast(corpus):
    db, storage = corpus
    with db() as s:  # 2 000 more articles
        s.add_all([ZannArticle(code=f"Z{n:09d}", lang="ru", ord=0, number="1", heading=f"Статья о предмете {n}",
                               act_title=f"Закон номер {n}", url="https://old.adilet.zan.kz/rus/docs/x",
                               text=f"Текст статьи {n} о регулировании отношений в сфере номер {n}. " * 5)
                   for n in range(2000)])
        s.commit()
    Indexer(db, storage).run()
    index = LawIndex(db)
    index.search("увольнение")  # warm up
    t0 = time.perf_counter()
    hits = index.search("выплата при увольнении работника")
    ms = (time.perf_counter() - t0) * 1000
    assert hits[0].number == "113" and ms < 1000  # SQLite scans in Python; PostgreSQL measured in docs


# ------------------------------------------------------------------ API and chat
def test_api_search_needs_internal_token(ctx, tmp_path):
    db, storage = ctx.container.session_factory, ctx.container.storage
    with db() as s:
        put_file(s, storage, TK, "ru", "Трудовой кодекс Республики Казахстан", TK_RU, "КОД")
    Indexer(db, storage).run()
    assert ctx.client.get("/v1/zann/search", params={"q": "увольнение"}).status_code == 403
    r = ctx.client.get("/v1/zann/search", params={"q": "выплата при увольнении", "lang": "ru"},
                       headers={"X-Admin-Token": "adm"})
    assert r.status_code == 200
    body = r.json()
    assert body["hits"][0]["citation"] == "ст. 113, Трудовой кодекс Республики Казахстан"
    assert body["hits"][0]["in_force"] is True and "text" not in body["hits"][0] and body["semantic"] is False
    r = ctx.client.get("/v1/zann/search", params={"q": "ст. 22 ТК", "full": "true"}, headers={"X-Bot-Secret": "bot"})
    assert r.json()["hits"][0]["article"] == "22" and "своевременную" in r.json()["hits"][0]["text"]
    assert ctx.client.get("/v1/zann/search", params={"q": "x", "lang": "en"},
                          headers={"X-Admin-Token": "adm"}).status_code == 422
    m = ctx.client.get("/v1/admin/metrics", headers={"X-Admin-Token": "adm"}).json()
    assert m["zann_index"]["articles"] == 4


def chat(index, turns, user_text):
    client = StreamingClient(turns)
    agent = ChatAgent(client, "claude-haiku-4-5", Adilet(fetch=fake_fetch), law_index=index)
    events = list(agent.stream([{"role": "user", "text": user_text}],
                               context={"pack": NS(country="KZ"), "forums": [], "case": {}, "lang": "ru"},
                               language="ru", country="Kazakhstan", use_portal=True))
    return events, client


def test_chat_gets_articles_from_the_index_and_cites_them(corpus):
    db, storage = corpus
    Indexer(db, storage).run()
    events, client = chat(LawIndex(db), [
        (["По ст. 113 Трудового кодекса расчёт — не позднее трёх рабочих дней."], "end_turn", [])],
        "Уволили, не выплатили расчёт при увольнении")
    system = client.calls[0]["system"]
    assert "ст. 113, Трудовой кодекс Республики Казахстан" in system and "#:~:text=" in system
    assert "law_search" in {t.get("name") for t in client.calls[0]["tools"]}
    res = events[-1]["result"]
    assert res.unchecked is False and res.norms[0]["act_code"] == TK and res.norms[0]["article"] == "113"
    assert "law_ms" in res.timing


def test_chat_law_search_tool(corpus):
    db, storage = corpus
    Indexer(db, storage).run()
    events, client = chat(LawIndex(db), [
        (["Посмотрю закон."], "tool_use", [tool_use("t1", "law_search", {"query": "возврат товара"})]),
        (["По ст. 9 Закона о защите прав потребителей товар можно вернуть за 14 дней."], "end_turn", [])],
        "Можно ли сдать обратно куртку?")
    sent = str(client.calls[1]["messages"])
    assert "ст. 9, О защите прав потребителей" in sent
    res = events[-1]["result"]
    assert res.unchecked is False and any(t["source"] == "index" for t in res.timing["tools"])


def test_chat_without_index_rows_has_no_law_search(db):
    events, client = chat(LawIndex(db), [(["Расскажите подробнее."], "end_turn", [])], "Уволили")
    assert "law_search" not in {t.get("name") for t in client.calls[0]["tools"]}
    assert "Articles for the last message" not in client.calls[0]["system"]
