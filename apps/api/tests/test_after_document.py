"""Owner 02.10 (screenshot: «on_hold» instead of the document; «отправь копию на email»):
- the mass-complaint limit counts the cases that reached a document, not every chat (each chat opens a case);
- «Копию мне на e-mail»: the document (PDF and Word) to the client's own confirmed e-mail, only once it is unlocked."""

from __future__ import annotations

import uuid

from konsilier.core.models import Case, User

from .test_e2e import web_user
from .test_payment import qualified_case


class Mailer:
    def __init__(self):
        self.sent = []

    def send_letter(self, **kw):
        self.sent.append(kw)
        return "id-1"


def test_many_chats_do_not_put_a_case_on_hold(ctx):
    api, cid = qualified_case(ctx)
    for i in range(12):  # twelve conversations, no documents
        api.post("/v1/cases", expect=201, json={"text": f"Вопрос номер {i}: сосед шумит по ночам", "country": "KZ",
                                                "defer": True})
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"], out
    with ctx.container.session_factory() as s:
        assert s.get(Case, uuid.UUID(cid)).hold_reason is None


def test_copy_to_me_needs_a_confirmed_email_and_an_unlocked_document(ctx):
    mailer = Mailer()
    ctx.container.claims_mailer = mailer
    api, cid = qualified_case(ctx)
    action = api.post(f"/v1/cases/{cid}/actions/next")["action_id"]
    r = api.c.post(f"/v1/cases/{cid}/actions/{action}/copy-to-me", headers=api.h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "email_required" and not mailer.sent
    with ctx.container.session_factory() as s:  # as after the sign-in by a code
        owner = s.get(User, s.get(Case, uuid.UUID(cid)).owner_id)
        owner.email = "client@example.com"
        s.commit()
    out = api.post(f"/v1/cases/{cid}/actions/{action}/copy-to-me")
    assert out["sent_to"] == "client@example.com"
    letter = mailer.sent[-1]
    assert letter["to"] == "client@example.com" and any(n.endswith(".docx") for n, _ in letter["attachments"])


def test_no_copy_of_someone_elses_document(ctx):
    ctx.container.claims_mailer = Mailer()
    api, cid = qualified_case(ctx)
    action = api.post(f"/v1/cases/{cid}/actions/next")["action_id"]
    other = web_user(ctx)
    r = other.c.post(f"/v1/cases/{cid}/actions/{action}/copy-to-me", headers=other.h)
    assert r.status_code in (403, 404)


def test_a_case_held_under_the_old_count_is_released_on_the_next_press(ctx):
    api, cid = qualified_case(ctx)
    with ctx.container.session_factory() as s:
        s.get(Case, uuid.UUID(cid)).hold_reason = "too_many_cases"
        s.commit()
    out = api.post(f"/v1/cases/{cid}/actions/next")
    assert out["action_id"]
