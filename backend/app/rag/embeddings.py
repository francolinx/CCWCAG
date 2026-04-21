"""Embeddings provider abstraction.

Defaults to a local sentence-transformers model so the system can run with no
API keys. If `EMBEDDINGS_PROVIDER=openai`, uses OpenAI embeddings. If neither
is available, falls back to a deterministic lightweight hashing embedding so
the pipeline stays runnable (quality degrades but nothing crashes).
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List, Optional, Sequence

from ..core.config import get_settings
from ..core.logging import get_logger

_log = get_logger(__name__)


class EmbeddingsProvider:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._kind = "hash"
        self._dim = 384
        self._st_model = None
        self._oa_client = None
        self._init_backend()

    def _init_backend(self) -> None:
        provider = (self._settings.embeddings_provider or "local").lower()
        if provider == "openai" and self._settings.openai_api_key:
            try:
                from openai import OpenAI

                self._oa_client = OpenAI(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                )
                self._kind = "openai"
                self._dim = 1536
                _log.info("embeddings: openai")
                return
            except Exception as e:
                _log.warning("openai embeddings init failed (%s); falling back", e)

        # Try local sentence-transformers.
        try:
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(self._settings.embeddings_model)
            self._kind = "local"
            self._dim = int(
                self._st_model.get_sentence_embedding_dimension()  # type: ignore
            )
            _log.info("embeddings: sentence-transformers (%s)", self._settings.embeddings_model)
            return
        except Exception as e:
            _log.warning(
                "sentence-transformers unavailable (%s); using deterministic hashing fallback", e
            )

        self._kind = "hash"
        self._dim = 384

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def kind(self) -> str:
        return self._kind

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._kind == "openai" and self._oa_client is not None:
            resp = self._oa_client.embeddings.create(
                model="text-embedding-3-small", input=list(texts)
            )
            return [d.embedding for d in resp.data]
        if self._kind == "local" and self._st_model is not None:
            vecs = self._st_model.encode(list(texts), normalize_embeddings=True).tolist()
            return [list(map(float, v)) for v in vecs]
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> List[float]:
        """Cheap reproducible fallback: word-hash buckets + L2-normalize."""
        dim = self._dim
        vec = [0.0] * dim
        tokens = re.findall(r"\w+", text.lower())
        for tok in tokens:
            h = int.from_bytes(hashlib.sha1(tok.encode()).digest()[:4], "big")
            vec[h % dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
