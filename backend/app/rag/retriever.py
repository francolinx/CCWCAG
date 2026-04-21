"""Retrieval over the WCAG corpus.

Queries the local Chroma collection (or the flat JSON store if Chroma isn't
available) and returns the top-k chunks with metadata and a cosine score.
Degrades gracefully — if the index hasn't been built yet, retrieval returns
an empty list and callers treat remediation as un-grounded.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger
from .embeddings import EmbeddingsProvider

_log = get_logger(__name__)

_COLLECTION = "wcag_corpus"


@dataclass
class RetrievedChunk:
    text: str
    metadata: Dict[str, Any]
    score: float


class WCAGRetriever:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._embeddings = EmbeddingsProvider()
        self._chroma = None
        self._flat: Optional[Dict[str, Any]] = None
        self._init_backend()

    def _init_backend(self) -> None:
        # Prefer Chroma.
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self._settings.vector_db_path)
            try:
                self._chroma = client.get_collection(_COLLECTION)
                _log.info("retriever: using chroma collection")
                return
            except Exception:
                pass
        except Exception:
            pass

        # Flat-file fallback.
        flat_path = Path(self._settings.vector_db_path) / "flat_store.json"
        if flat_path.exists():
            try:
                self._flat = json.loads(flat_path.read_text(encoding="utf-8"))
                _log.info("retriever: using flat-file store")
            except Exception as e:
                _log.warning("failed to load flat store: %s", e)
                self._flat = None

    @property
    def ready(self) -> bool:
        return self._chroma is not None or self._flat is not None

    def search(self, query: str, top_k: int = 4) -> List[RetrievedChunk]:
        if not query or not query.strip():
            return []
        if not self.ready:
            return []
        vec = self._embeddings.embed([query])[0]

        if self._chroma is not None:
            res = self._chroma.query(
                query_embeddings=[vec],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            out: List[RetrievedChunk] = []
            for doc, meta, dist in zip(docs, metas, dists):
                # Chroma cosine distance → similarity in [0,1]
                score = max(0.0, 1.0 - float(dist))
                out.append(RetrievedChunk(text=doc, metadata=dict(meta or {}), score=score))
            return out

        # Flat fallback.
        assert self._flat is not None
        items = self._flat.get("items", [])
        scored: List[RetrievedChunk] = []
        for it in items:
            sim = _cosine(vec, it["vector"])
            scored.append(
                RetrievedChunk(text=it["text"], metadata=dict(it.get("metadata") or {}), score=sim)
            )
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return float(num / (na * nb))


# Convenience singleton.
_retriever: Optional[WCAGRetriever] = None


def get_retriever() -> WCAGRetriever:
    global _retriever
    if _retriever is None:
        _retriever = WCAGRetriever()
    return _retriever
