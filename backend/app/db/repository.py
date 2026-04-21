"""Thin repository helpers over the ORM."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.orm import Finding, Page, Scan, ScanComparison


def new_id() -> str:
    return uuid.uuid4().hex


# ---------- scans ----------

async def create_scan(session: AsyncSession, **fields: Any) -> Scan:
    scan = Scan(id=new_id(), **fields)
    session.add(scan)
    await session.flush()
    return scan


async def get_scan(session: AsyncSession, scan_id: str) -> Optional[Scan]:
    q = select(Scan).where(Scan.id == scan_id)
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def update_scan(session: AsyncSession, scan_id: str, **fields: Any) -> None:
    scan = await get_scan(session, scan_id)
    if not scan:
        return
    for k, v in fields.items():
        setattr(scan, k, v)
    scan.updated_at = datetime.utcnow()
    await session.flush()


async def list_scans(
    session: AsyncSession, domain: Optional[str] = None, limit: int = 50
) -> List[Scan]:
    q = select(Scan).order_by(Scan.created_at.desc()).limit(limit)
    if domain:
        q = q.where(Scan.domain == domain)
    res = await session.execute(q)
    return list(res.scalars().all())


async def list_scans_for_domain(
    session: AsyncSession, domain: str, exclude_id: Optional[str] = None
) -> List[Scan]:
    q = select(Scan).where(Scan.domain == domain).order_by(Scan.created_at.desc())
    res = await session.execute(q)
    scans = list(res.scalars().all())
    if exclude_id:
        scans = [s for s in scans if s.id != exclude_id]
    return scans


# ---------- pages ----------

async def create_page(session: AsyncSession, **fields: Any) -> Page:
    page = Page(id=new_id(), **fields)
    session.add(page)
    await session.flush()
    return page


async def get_pages(session: AsyncSession, scan_id: str) -> List[Page]:
    q = (
        select(Page)
        .where(Page.scan_id == scan_id)
        .order_by(Page.priority.desc(), Page.created_at.asc())
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def update_page(session: AsyncSession, page_id: str, **fields: Any) -> None:
    q = select(Page).where(Page.id == page_id)
    res = await session.execute(q)
    page = res.scalar_one_or_none()
    if not page:
        return
    for k, v in fields.items():
        setattr(page, k, v)
    await session.flush()


# ---------- findings ----------

async def create_finding(session: AsyncSession, **fields: Any) -> Finding:
    finding = Finding(id=new_id(), **fields)
    session.add(finding)
    await session.flush()
    return finding


async def get_findings(session: AsyncSession, scan_id: str) -> List[Finding]:
    q = (
        select(Finding)
        .where(Finding.scan_id == scan_id)
        .options(selectinload(Finding.page))
        .order_by(Finding.severity.asc(), Finding.created_at.asc())
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def update_finding(session: AsyncSession, finding_id: str, **fields: Any) -> None:
    q = select(Finding).where(Finding.id == finding_id)
    res = await session.execute(q)
    f = res.scalar_one_or_none()
    if not f:
        return
    for k, v in fields.items():
        setattr(f, k, v)
    await session.flush()


# ---------- comparisons ----------

async def save_comparison(
    session: AsyncSession, scan_id: str, previous_scan_id: str, summary: Dict[str, Any]
) -> ScanComparison:
    comp = ScanComparison(
        id=new_id(),
        scan_id=scan_id,
        previous_scan_id=previous_scan_id,
        summary_json=summary,
    )
    session.add(comp)
    await session.flush()
    return comp
