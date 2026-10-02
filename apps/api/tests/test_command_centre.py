"""Command centre (/ops app): the team's files served read-only to the owner (admin token), from TEAM_DIR or GitHub,
cached; 503 when the source cannot be read; the owner confirms payments; metrics count real payments."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from konsilier.api import command

from .test_e2e import ADMIN
from .test_payment import confirm, manual, qualified_case


@pytest.fixture(autouse=True)
def fresh_cache():
    command.clear_cache()
    yield
    command.clear_cache()


def team_dir(tmp_path: Path) -> Path:
    root = tmp_path / "branch"
    (root / "team" / "reports").mkdir(parents=True)
    (root / "team" / "leads").mkdir()
    (root / "team" / "sessions.md").write_text("| Сессия | Ветка |\n|---|---|\n| [A](https://x) | `b` |\n", "utf-8")
    (root / "team" / "decisions.md").write_text("| Дата | Решение | Источник |\n|---|---|---|\n", "utf-8")
    (root / "team" / "README.md").write_text("# Команда\n", "utf-8")
    (root / "team" / "reports" / "2026-09-29-pm.md").write_text("# Вечер 29.09\n", "utf-8")
    (root / "team" / "reports" / "2026-09-30-am.md").write_text("# Утро 30.09\n", "utf-8")
    (root / "team" / "leads" / "lawyers.csv").write_text("name,city\nA,B\n", "utf-8")
    (root / "team" / "deck.pdf").write_bytes(b"%PDF")  # not served: only .md / .csv
    (root / "secret.md").write_text("outside team/", "utf-8")
    return root


def test_admin_token_required(ctx):
    for path in ("/v1/admin/team/files", "/v1/admin/team/sessions", "/v1/admin/team/reports",
                 "/v1/admin/team/file?path=team/README.md", "/v1/admin/team/bundle", "/v1/admin/payments"):
        assert ctx.client.get(path).status_code == 403
        assert ctx.client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 403


def test_files_from_team_dir(ctx, tmp_path):
    ctx.container.settings.team_dir = str(team_dir(tmp_path))
    c, h = ctx.client, ADMIN
    files = c.get("/v1/admin/team/files", headers=h).json()
    assert files["source"] == "dir"
    assert [f["path"] for f in files["files"]] == [
        "team/README.md", "team/decisions.md", "team/leads/lawyers.csv", "team/reports/2026-09-29-pm.md",
        "team/reports/2026-09-30-am.md", "team/sessions.md"]
    assert c.get("/v1/admin/team/sessions", headers=h).json()["text"].startswith("| Сессия")
    assert c.get("/v1/admin/team/decisions", headers=h).json()["path"] == "team/decisions.md"
    assert c.get("/v1/admin/team/reports", headers=h).json()["reports"] == [
        {"name": "2026-09-30-am.md", "path": "team/reports/2026-09-30-am.md"},
        {"name": "2026-09-29-pm.md", "path": "team/reports/2026-09-29-pm.md"}]  # newest first
    assert c.get("/v1/admin/team/reports/2026-09-30-am.md", headers=h).json()["text"] == "# Утро 30.09\n"
    assert c.get("/v1/admin/team/file?path=team/leads/lawyers.csv", headers=h).json()["text"].startswith("name,")
    # a file the team adds later shows up without code changes
    (Path(ctx.container.settings.team_dir) / "team" / "new-plan.md").write_text("# Новое", "utf-8")
    command.clear_cache()
    assert c.get("/v1/admin/team/file?path=team/new-plan.md", headers=h).json()["text"] == "# Новое"

    bundle = c.get("/v1/admin/team/bundle", headers=h).json()
    assert bundle["texts"]["team/sessions.md"].startswith("| Сессия")
    assert bundle["texts"]["team/backlog.md"] is None  # not there (yet): null, not an error
    assert bundle["texts"]["team/reports/2026-09-30-am.md"] == "# Утро 30.09\n"
    assert bundle["reports"][0]["name"] == "2026-09-30-am.md"


def test_only_team_md_and_csv(ctx, tmp_path):
    ctx.container.settings.team_dir = str(team_dir(tmp_path))
    c, h = ctx.client, ADMIN
    for bad in ("secret.md", "team/../secret.md", "team/deck.pdf", "/etc/passwd", "team/reports/../../secret.md",
                "team/", "team/README.md/"):
        assert c.get("/v1/admin/team/file", params={"path": bad}, headers=h).status_code == 400, bad
    assert c.get("/v1/admin/team/reports/..%2F..%2Fsecret.md", headers=h).status_code in (400, 404)
    assert c.get("/v1/admin/team/file?path=team/missing.md", headers=h).status_code == 404
    assert c.get("/v1/admin/team/file?path=team/missing.md", headers=h).json()["detail"]["code"] == "not_found"


class FakeGitHub:
    """httpx.get stand-in: the git tree API and raw / contents API answers."""

    def __init__(self, status: int = 200):
        self.status = status
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers: dict | None = None, **_):
        self.calls.append((url, headers or {}))
        req = httpx.Request("GET", url)
        if self.status != 200:
            return httpx.Response(self.status, request=req)
        if "/git/trees/" in url:
            return httpx.Response(200, request=req, json={"tree": [
                {"path": "team", "type": "tree"},
                {"path": "team/sessions.md", "type": "blob", "size": 10},
                {"path": "team/reports/2026-09-30-am.md", "type": "blob", "size": 5},
                {"path": "team/grants/deck.pdf", "type": "blob", "size": 5},
                {"path": "apps/api/x.md", "type": "blob", "size": 5},
            ]})
        if url.endswith("team/sessions.md") or "contents/team/sessions.md" in url:
            return httpx.Response(200, request=req, content="| Сессия |".encode())
        return httpx.Response(404, request=req)


def test_github_public_raw_and_cache(ctx, monkeypatch):
    st = ctx.container.settings
    st.team_dir, st.team_github_token = "", ""
    gh = FakeGitHub()
    monkeypatch.setattr(command.httpx, "get", gh)
    c, h = ctx.client, ADMIN
    files = c.get("/v1/admin/team/files", headers=h).json()
    assert files["source"] == "github"
    assert [f["path"] for f in files["files"]] == ["team/reports/2026-09-30-am.md", "team/sessions.md"]
    assert "api.github.com/repos/gigrosscom/legal-autopilot/git/trees/claude%2Fai-team" in gh.calls[0][0]
    assert c.get("/v1/admin/team/sessions", headers=h).json()["text"] == "| Сессия |"
    raw = gh.calls[-1]
    assert raw[0] == "https://raw.githubusercontent.com/gigrosscom/legal-autopilot/claude/ai-team/team/sessions.md"
    assert "Authorization" not in raw[1]
    n = len(gh.calls)
    c.get("/v1/admin/team/sessions", headers=h)
    c.get("/v1/admin/team/files", headers=h)
    assert len(gh.calls) == n  # cached for TEAM_CACHE_SECONDS
    assert c.get("/v1/admin/team/decisions", headers=h).status_code == 404


def test_github_private_with_token(ctx, monkeypatch):
    st = ctx.container.settings
    st.team_dir, st.team_github_token = "", "tok-test"
    gh = FakeGitHub()
    monkeypatch.setattr(command.httpx, "get", gh)
    assert ctx.client.get("/v1/admin/team/sessions", headers=ADMIN).json()["text"] == "| Сессия |"
    url, headers = gh.calls[-1]
    assert url.startswith("https://api.github.com/repos/gigrosscom/legal-autopilot/contents/team/sessions.md?ref=")
    assert headers["Authorization"] == "Bearer tok-test" and headers["Accept"] == "application/vnd.github.raw"


@pytest.mark.parametrize("status", [401, 403, 500])
def test_unavailable_is_503(ctx, monkeypatch, status):
    ctx.container.settings.team_dir = ""
    monkeypatch.setattr(command.httpx, "get", FakeGitHub(status))
    for path in ("/v1/admin/team/files", "/v1/admin/team/sessions", "/v1/admin/team/bundle", "/v1/admin/team/reports"):
        r = ctx.client.get(path, headers=ADMIN)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "team_unavailable", path


def test_network_error_is_503_and_not_cached(ctx, monkeypatch):
    ctx.container.settings.team_dir = ""

    def down(*_, **__):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(command.httpx, "get", down)
    assert ctx.client.get("/v1/admin/team/sessions", headers=ADMIN).status_code == 503
    monkeypatch.setattr(command.httpx, "get", FakeGitHub())
    assert ctx.client.get("/v1/admin/team/sessions", headers=ADMIN).status_code == 200


def test_team_dir_without_team_folder_is_503(ctx, tmp_path):
    ctx.container.settings.team_dir = str(tmp_path / "nowhere")
    r = ctx.client.get("/v1/admin/team/files", headers=ADMIN)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "team_unavailable"


def test_owner_confirms_payment_and_metrics_count_it(ctx):
    manual(ctx)
    api, cid = qualified_case(ctx)
    confirm(api)
    code = api.post(f"/v1/cases/{cid}/payment", json={"purpose": "document"})["case"]["payment"]["code"]
    api.post(f"/v1/cases/{cid}/payment/claim")
    m = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()
    assert m["payments"]["awaiting_confirmation"] == 1 and m["payments"]["paid"] == 0
    assert set(m["today"]) == {"users", "cases", "documents"} and m["today"]["cases"] >= 1

    rows = ctx.client.get("/v1/admin/payments", headers=ADMIN).json()
    assert [r["code"] for r in rows] == [code]
    ok = ctx.client.post(f"/v1/admin/payments/{rows[0]['id']}", headers=ADMIN, json={"decision": "paid"}).json()
    assert ok["status"] == "paid" and ok["decided_by"] == "owner (command centre)"
    assert ctx.client.get("/v1/admin/payments", headers=ADMIN).json() == []
    assert ctx.client.post(f"/v1/admin/payments/{rows[0]['id']}", headers=ADMIN,
                           json={"decision": "not_found"}).status_code == 409
    assert api.get(f"/v1/cases/{cid}").json()["payment"]["credits"] == 1

    p = ctx.client.get("/v1/admin/metrics", headers=ADMIN).json()["payments"]
    assert p["paid"] == 1 and p["paid_clients"] == 1 and p["paid_today"] == 1
    assert p["revenue"] == {"KZT": "2990.00"} and p["awaiting_confirmation"] == 0
