"""Optional semantic vectors for the Zann search: a free open multilingual model run on the server's CPU.

ZANN_EMBEDDINGS=off (default) — words search only. ZANN_EMBEDDINGS=e5-small — intfloat/multilingual-e5-small
(MIT licence, 118 M parameters, 384 dimensions, XLM-R vocabulary covering kk), the smallest good multilingual model.
Measured 01.10.2026 on 4 shared vCPU under load: ≈4 passages/s, ≈0.9 s per query — too slow for the chat (which uses
words only) and for the whole corpus on the server; vectors of the whole corpus are better computed on a free GPU
and loaded into the table. Measure on the server with ``python -m konsilier.cli zann-index --embed-only --minutes 1``.
No paid API, nothing leaves the server.

The model is loaded lazily from sentence-transformers (``pip install sentence-transformers``, which brings torch
and numpy; not a dependency of the API image unless embeddings are switched on). Vectors are L2-normalised and
stored as float16 bytes (768 bytes each) in zann_articles.embedding; cosine is then a dot product, done with numpy
over an in-memory matrix — pgvector is not required.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

log = logging.getLogger(__name__)

MODELS = {"e5-small": "intfloat/multilingual-e5-small"}
PASSAGE_CHARS = 2000  # the model reads ≈512 tokens; the start of an article (heading and first parts) is what counts


class Embedder(Protocol):
    name: str  # stored in zann_articles.emb_model
    dim: int

    def passages(self, texts: list[str]) -> list[list[float]]: ...

    def query(self, text: str) -> list[float]: ...


class E5Embedder:
    """multilingual-e5: «query: » / «passage: » prefixes as its card asks; normalised vectors."""

    def __init__(self, key: str = "e5-small", device: str = "cpu", batch_size: int = 16):
        self.name, self.model_id, self.device, self.batch_size = key, MODELS[key], device, batch_size
        self.dim = 384
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer  # optional dependency

                self._model = SentenceTransformer(self.model_id, device=self.device)
                self.dim = int(self._model.get_sentence_embedding_dimension())
        return self._model

    def passages(self, texts: list[str]) -> list[list[float]]:
        m = self._load()
        vecs = m.encode(["passage: " + t[:PASSAGE_CHARS] for t in texts], batch_size=self.batch_size,
                        normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]

    def query(self, text: str) -> list[float]:
        v = self._load().encode(["query: " + text[:1000]], normalize_embeddings=True, show_progress_bar=False)[0]
        return list(map(float, v))


def build_embedder(setting: str | None) -> Embedder | None:
    key = (setting or "off").strip().lower()
    if key in ("", "off", "none", "false", "0"):
        return None
    if key not in MODELS:
        log.warning("ZANN_EMBEDDINGS=%s is unknown (known: off, %s): semantic search off", key, ", ".join(MODELS))
        return None
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        log.warning("ZANN_EMBEDDINGS=%s needs sentence-transformers and numpy: semantic search off", key)
        return None
    return E5Embedder(key)


# ---------------------------------------------------------------------------------------------------- packing
def pack(vec: list[float]) -> bytes:
    """float16 little-endian bytes of a normalised vector."""
    import struct

    return struct.pack(f"<{len(vec)}e", *vec)


def unpack(data: bytes) -> list[float]:
    import struct

    return list(struct.unpack(f"<{len(data) // 2}e", data))


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorTable:
    """All vectors of one model in memory (ids + matrix), reloaded when the number of rows changed. numpy when
    available (the embeddings extra brings it); pure Python otherwise (tests, small indexes)."""

    def __init__(self) -> None:
        self.ids: list[int] = []
        self.matrix: Any = None
        self.rows: list[list[float]] = []
        self.count = -1

    def load(self, items: list[tuple[int, bytes]]) -> None:
        self.ids = [i for i, _ in items]
        try:
            import numpy as np

            self.matrix = (np.frombuffer(b"".join(b for _, b in items), dtype="<f2").reshape(len(items), -1)
                           if items else None)
            self.rows = []
        except ImportError:
            self.matrix, self.rows = None, [unpack(b) for _, b in items]
        self.count = len(items)

    def top(self, q: list[float], k: int) -> list[tuple[int, float]]:
        if not self.ids:
            return []
        if self.matrix is not None:
            import numpy as np

            qv = np.asarray(q, dtype=np.float32)
            # float16 rows are kept (half the memory); converted block by block for a fast float32 product
            sims = np.concatenate([self.matrix[i:i + 50_000].astype(np.float32) @ qv
                                   for i in range(0, len(self.ids), 50_000)])
            k = min(k, len(sims))
            idx = np.argpartition(-sims, k - 1)[:k]
            idx = idx[np.argsort(-sims[idx])]
            return [(self.ids[i], float(sims[i])) for i in idx]
        scored = sorted(((dot(r, q), i) for i, r in zip(self.ids, self.rows)), reverse=True)[:k]
        return [(i, s) for s, i in scored]
