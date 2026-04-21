"""Health, public config, and a small WCAG search endpoint."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query

from ..core.config import get_settings
from ..models.schemas import PublicConfig, WcagSearchHit
from ..rag.retriever import get_retriever

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {"status": "ok", "env": s.app_env}


@router.get("/config", response_model=PublicConfig)
async def config() -> PublicConfig:
    s = get_settings()
    return PublicConfig(
        app_env=s.app_env,
        model_provider=s.model_provider,
        model_name=s.model_name,
        llm_enabled=s.llm_enabled,
        embeddings_provider=s.embeddings_provider,
        default_crawl_depth=s.default_crawl_depth,
        default_page_limit=s.default_page_limit,
    )


@router.get("/wcag/search", response_model=List[WcagSearchHit])
async def wcag_search(
    q: str = Query(..., min_length=2, max_length=200),
    top_k: int = Query(5, ge=1, le=20),
) -> List[WcagSearchHit]:
    retriever = get_retriever()
    if not retriever.ready:
        return []
    hits = retriever.search(q, top_k=top_k)
    return [
        WcagSearchHit(
            criterion=h.metadata.get("criterion", "WCAG"),
            url=h.metadata.get("url"),
            snippet=h.text[:600],
            score=h.score,
        )
        for h in hits
    ]
