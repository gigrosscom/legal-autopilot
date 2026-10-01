"""Zann search API («ищет и цитирует»): GET /v1/zann/search?q=&lang=&limit= — articles of the collected adilet acts
that answer the question, each with its citation («ст. 113, Трудовой кодекс …») and the adilet link. Internal: the
admin token (X-Admin-Token) or the bot secret (X-Bot-Secret). No LLM, no paid service: PostgreSQL full text (and,
with ZANN_EMBEDDINGS on, a CPU embedding model)."""

from __future__ import annotations

import hmac
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..container import Container
from .deps import get_container

router = APIRouter(prefix="/v1/zann")


def require_internal(x_admin_token: str | None = Header(default=None), x_bot_secret: str | None = Header(default=None),
                     container: Container = Depends(get_container)) -> None:
    s = container.settings
    if x_admin_token and s.admin_token and hmac.compare_digest(x_admin_token, s.admin_token):
        return
    if x_bot_secret and s.bot_api_secret and hmac.compare_digest(x_bot_secret, s.bot_api_secret):
        return
    raise HTTPException(403, "admin token or bot secret required")


@router.get("/search", dependencies=[Depends(require_internal)])
def zann_search(q: str = Query(..., min_length=2, max_length=500), lang: str | None = Query(None, pattern="^(ru|kk)$"),
                limit: int = Query(5, ge=1, le=20), full: bool = False,
                container: Container = Depends(get_container)) -> dict[str, Any]:
    index = container.law_index
    if index is None:
        raise HTTPException(503, "zann search is not configured")
    t0 = time.perf_counter()
    hits = index.search(q, lang=lang, limit=limit, min_score=0)
    return {"query": q, "lang": lang, "took_ms": round((time.perf_counter() - t0) * 1000, 1),
            "semantic": index.embedder is not None, "hits": [h.public(full) for h in hits]}
