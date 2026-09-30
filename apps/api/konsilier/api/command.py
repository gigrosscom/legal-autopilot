"""Command centre (/ops app) for the owner: the team's files, read-only, and the payments to confirm.

The AI team keeps its memory in a git branch (team/: sessions.md, decisions.md, backlog.md, plan-month-1.md,
reports/…), not in the database. These endpoints serve those files as text to the owner's app:

- TEAM_DIR set → read from that folder on disk (a checkout of the branch; the folder that holds team/);
- otherwise → GitHub (TEAM_GITHUB_REPO at TEAM_GITHUB_REF): the git tree API for the listing and the contents API
  (with TEAM_GITHUB_TOKEN, private repository) or raw.githubusercontent.com (public) for a file.

Only team/**.md and team/**.csv are served. Answers are cached TEAM_CACHE_SECONDS; when the source cannot be read the
answer is 503 {"code": "team_unavailable"} and the app says so.

Access: the admin token (X-Admin-Token), as /admin and /v1/admin/metrics.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..container import Container
from ..core.models import Invoice
from .deps import get_container, get_session, require_admin
from .ops import _test_users, decide_invoice, invoice_view

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])
log = logging.getLogger(__name__)

ROOT = "team/"
SUFFIXES = (".md", ".csv")
MAX_BYTES = 2_000_000
# letters (any script), digits, dot, dash, underscore and slashes; no "..", no leading slash
_PATH = re.compile(r"^team/(?:[\w.\-]+/)*[\w.\-]+\.(?:md|csv)$")
# the files the app needs on every open, fetched in one call (GET /team/bundle)
CORE = ("team/README.md", "team/sessions.md", "team/decisions.md", "team/backlog.md", "team/plan-month-1.md")

_cache: dict[tuple[str, ...], tuple[float, Any]] = {}


def clear_cache() -> None:
    _cache.clear()


class TeamUnavailable(Exception):
    pass


class NotFound(Exception):
    pass


def valid_path(path: str) -> bool:
    return bool(_PATH.match(path)) and ".." not in path.split("/")


def _source(settings: Settings) -> tuple[str, ...]:
    if settings.team_dir:
        return ("dir", settings.team_dir)
    return ("github", settings.team_github_repo, settings.team_github_ref)


def _cached(settings: Settings, key: tuple[str, ...], load) -> Any:
    k = _source(settings) + key
    hit = _cache.get(k)
    now = time.monotonic()
    if hit is not None and now - hit[0] < settings.team_cache_seconds:
        return hit[1]
    value = load()  # failures are not cached: the next open tries again
    _cache[k] = (now, value)
    return value


def _github(settings: Settings, url: str, raw: bool = False) -> httpx.Response:
    headers = {"User-Agent": "konsilier-command-centre"}
    if settings.team_github_token:
        headers["Authorization"] = f"Bearer {settings.team_github_token}"
    if raw:
        headers["Accept"] = "application/vnd.github.raw"
    try:
        return httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
    except httpx.HTTPError as e:
        raise TeamUnavailable(type(e).__name__) from e


def list_files(settings: Settings) -> list[dict[str, Any]]:
    """Every team/**.md and team/**.csv: [{path, size}], sorted by path."""
    def load() -> list[dict[str, Any]]:
        if settings.team_dir:
            base = Path(settings.team_dir)
            if not (base / "team").is_dir():
                raise TeamUnavailable("TEAM_DIR has no team/ folder")
            out = [{"path": p.relative_to(base).as_posix(), "size": p.stat().st_size}
                   for p in (base / "team").rglob("*") if p.is_file() and p.suffix in SUFFIXES]
        else:
            r = _github(settings, f"https://api.github.com/repos/{settings.team_github_repo}/git/trees/"
                                  f"{quote(settings.team_github_ref, safe='')}?recursive=1")
            if r.status_code != 200:
                raise TeamUnavailable(f"github tree {r.status_code}")
            out = [{"path": t["path"], "size": t.get("size", 0)} for t in r.json().get("tree", [])
                   if t.get("type") == "blob" and t["path"].startswith(ROOT) and t["path"].endswith(SUFFIXES)]
        return sorted((f for f in out if valid_path(f["path"])), key=lambda f: f["path"])
    return _cached(settings, ("list",), load)


def read_file(settings: Settings, path: str) -> str:
    if not valid_path(path):
        raise NotFound(path)

    def load() -> str:
        if settings.team_dir:
            base = Path(settings.team_dir).resolve()
            p = (base / path).resolve()
            if not p.is_relative_to(base / "team"):
                raise NotFound(path)
            if not (base / "team").is_dir():
                raise TeamUnavailable("TEAM_DIR has no team/ folder")
            if not p.is_file():
                raise NotFound(path)
            if p.stat().st_size > MAX_BYTES:
                raise NotFound(path)
            return p.read_text(encoding="utf-8", errors="replace")
        repo, ref = settings.team_github_repo, settings.team_github_ref
        if settings.team_github_token:
            r = _github(settings, f"https://api.github.com/repos/{repo}/contents/{quote(path)}?ref={quote(ref, safe='')}",
                        raw=True)
        else:
            r = _github(settings, f"https://raw.githubusercontent.com/{repo}/{ref}/{quote(path)}")
        if r.status_code == 404:
            raise NotFound(path)
        if r.status_code != 200:
            raise TeamUnavailable(f"github file {r.status_code}")
        if len(r.content) > MAX_BYTES:
            raise NotFound(path)
        return r.content.decode("utf-8", errors="replace")
    return _cached(settings, ("file", path), load)


def _serve(settings: Settings, fn, *args) -> Any:
    try:
        return fn(settings, *args)
    except NotFound as e:
        raise HTTPException(404, {"code": "not_found", "message": "not_found"}) from e
    except TeamUnavailable as e:
        log.warning("team files unavailable: %s", e)
        raise HTTPException(503, {"code": "team_unavailable", "message": "team_unavailable"}) from e


def _text(settings: Settings, path: str) -> dict[str, str]:
    return {"path": path, "text": _serve(settings, read_file, path)}


def _reports(settings: Settings) -> list[dict[str, str]]:
    files = _serve(settings, list_files)
    names = [f["path"][len("team/reports/"):] for f in files
             if f["path"].startswith("team/reports/") and f["path"].endswith(".md") and f["path"].count("/") == 2]
    return [{"name": n, "path": f"team/reports/{n}"} for n in sorted(names, reverse=True)]


@router.get("/team/files")
def team_files(container: Container = Depends(get_container)) -> dict[str, Any]:
    s = container.settings
    return {"source": _source(s)[0], "files": _serve(s, list_files)}


@router.get("/team/file")
def team_file(path: str, container: Container = Depends(get_container)) -> dict[str, str]:
    if not valid_path(path):
        raise HTTPException(400, {"code": "bad_path", "message": "only team/**.md and team/**.csv"})
    return _text(container.settings, path)


@router.get("/team/bundle")
def team_bundle(container: Container = Depends(get_container)) -> dict[str, Any]:
    """What the app shows on open, in one call: the file list, the core files and the latest report. A core file
    that does not exist (yet) is null."""
    s = container.settings
    files = _serve(s, list_files)
    reports = _reports(s)
    texts: dict[str, str | None] = {}
    for path in CORE + ((reports[0]["path"],) if reports else ()):
        try:
            texts[path] = read_file(s, path)
        except NotFound:
            texts[path] = None
        except TeamUnavailable as e:
            log.warning("team files unavailable: %s", e)
            raise HTTPException(503, {"code": "team_unavailable", "message": "team_unavailable"}) from e
    return {"source": _source(s)[0], "repo": None if s.team_dir else s.team_github_repo,
            "ref": None if s.team_dir else s.team_github_ref, "files": files,
            "reports": reports, "texts": texts}


@router.get("/team/sessions")
def team_sessions(container: Container = Depends(get_container)) -> dict[str, str]:
    return _text(container.settings, "team/sessions.md")


@router.get("/team/decisions")
def team_decisions(container: Container = Depends(get_container)) -> dict[str, str]:
    return _text(container.settings, "team/decisions.md")


@router.get("/team/reports")
def team_reports(container: Container = Depends(get_container)) -> dict[str, Any]:
    return {"reports": _reports(container.settings)}


@router.get("/team/reports/{name}")
def team_report(name: str, container: Container = Depends(get_container)) -> dict[str, str]:
    path = f"team/reports/{name}"
    if "/" in name or not valid_path(path) or not name.endswith(".md"):
        raise HTTPException(400, {"code": "bad_path", "message": "bad report name"})
    return _text(container.settings, path)


# ------------------------------------------------------------------ payments waiting for the owner's confirmation
@router.get("/payments")
def payments(status: str | None = "awaiting_confirmation", session: Session = Depends(get_session),
             container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    """The clients desk's document payments by transfer (same list as /v1/ops/clients/payments), for the owner."""
    q = select(Invoice).where(Invoice.method != "stub", Invoice.user_id.not_in(_test_users())) \
        .order_by(Invoice.created_at.desc()).limit(200)
    if status:
        q = q.where(Invoice.status == status)
    return [invoice_view(session, container, inv) for inv in session.scalars(q).all()]


class OwnerPaymentDecision(BaseModel):
    decision: Literal["paid", "not_found"]
    note: str | None = Field(default=None, max_length=4000)


@router.post("/payments/{invoice_id}")
def decide(invoice_id: int, body: OwnerPaymentDecision, session: Session = Depends(get_session),
           container: Container = Depends(get_container)) -> dict[str, Any]:
    return decide_invoice(session, container, invoice_id, "owner (command centre)", body.decision == "paid", body.note)
