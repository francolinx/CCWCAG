"""Async background worker that drives a scan end-to-end.

For an MVP we use plain asyncio background tasks. That's reliable (no extra
infra like Redis or Celery) and works well behind a single uvicorn process.
Swapping to a real queue is a file-level change later.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from ..agents.graph import run_scan_graph
from ..core.logging import get_logger
from ..db.base import session_scope
from ..db.repository import update_scan

_log = get_logger(__name__)


async def run_scan(scan_id: str, options: Dict[str, Any], root_url: str, domain: str) -> None:
    async with session_scope() as session:
        await update_scan(session, scan_id, status="running")

    initial: Dict[str, Any] = {
        "scan_id": scan_id,
        "root_url": root_url,
        "domain": domain,
        "options": options,
        "planned_pages": [],
        "captures": [],
        "findings": [],
        "errors": [],
        "stats": {},
    }
    try:
        await run_scan_graph(initial)
    except Exception as e:
        _log.exception("scan %s failed: %s", scan_id, e)
        async with session_scope() as session:
            await update_scan(session, scan_id, status="failed", error=str(e))


def schedule(scan_id: str, options: Dict[str, Any], root_url: str, domain: str) -> None:
    """Fire-and-forget: schedule run_scan on the current event loop."""
    loop = asyncio.get_event_loop()
    loop.create_task(run_scan(scan_id, options, root_url, domain))
