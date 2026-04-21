"""Quick retrieval smoke: ingest corpus, ask for 'alt text'."""
from __future__ import annotations

import os

import pytest


@pytest.mark.integration
def test_rag_roundtrip(tmp_path, monkeypatch):
    # Redirect vector store to a tmp dir so this never pollutes the dev DB.
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "vec"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))

    from backend.app.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    from backend.app.rag.ingest import ingest
    from backend.app.rag.retriever import WCAGRetriever

    result = ingest()
    assert result["chunks"] > 0

    r = WCAGRetriever()
    hits = r.search("missing alt text on images", top_k=3)
    assert hits, "retrieval should return at least one hit"
    top = hits[0]
    assert "1.1.1" in (top.metadata.get("criterion") or "")
