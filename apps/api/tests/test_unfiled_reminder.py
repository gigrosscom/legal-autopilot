"""QA BUG-19: no case had a response deadline — it starts when the document is marked filed, and nobody marked it.
A ready, paid document left unmarked gets one reminder a day later (with the date the answer would be due if filed
today); the case shows that date before filing too."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from konsilier.api.delivery import unfiled
from konsilier.core.models import Notification

from .test_email_delivery import case, url  # noqa: F401 — the fixture


def _notes(ctx):
    with ctx.container.session_factory() as s:
        return [n.text for n in s.query(Notification).filter(Notification.kind == "delivery")]


def test_a_ready_document_not_marked_filed_is_asked_about_once(case):  # noqa: F811
    ctx, api, cid, aid = case
    job = unfiled(ctx.container)
    now = datetime.now(timezone.utc)
    with ctx.container.session_factory() as s:
        assert job(s, now) == 0  # just made
        assert job(s, now + timedelta(hours=25)) == 1
        s.commit()
        assert job(s, now + timedelta(hours=50)) == 0  # once
        s.commit()
    [text] = _notes(ctx)
    assert "Document filed" in text and "due by" in text


def test_a_filed_document_is_not_asked_about(case):  # noqa: F811
    ctx, api, cid, aid = case
    api.post(url(cid, aid, "/submitted"), json={})
    with ctx.container.session_factory() as s:
        assert unfiled(ctx.container)(s, datetime.now(timezone.utc) + timedelta(hours=25)) == 0


def test_the_case_shows_the_reply_date_before_filing(case):  # noqa: F811
    ctx, api, cid, aid = case
    a = api.get(f"/v1/cases/{cid}").json()["actions"][0]
    assert a["status"] == "ready" and a["deadline"] is None
    assert a["filing"]["response"]["if_filed_today"]
