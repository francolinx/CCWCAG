"""Scan-related REST endpoints.

All responses use the Pydantic schemas from `app.models.schemas`, so both
OpenAPI docs and client SDKs get accurate types.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import get_settings
from ..db.repository import (
    create_scan,
    get_findings,
    get_pages,
    get_scan,
    list_scans,
    list_scans_for_domain,
    save_comparison,
)
from ..models.orm import Finding, Page, Scan, ScanComparison
from ..models.schemas import (
    CompareResult,
    FindingOut,
    FindingsByPage,
    PageOut,
    Remediation,
    ScanCreate,
    ScanDetail,
    ScanFindings,
    ScanListItem,
    ScanOut,
    WcagReference,
)
from ..utils.paths import to_public_url
from ..utils.url import canonical_domain
from ..workers.scan_runner import schedule
from .deps import get_session

router = APIRouter(prefix="/api", tags=["scans"])


# ---------- create / read ----------

@router.post("/scans", response_model=ScanOut, status_code=201)
async def start_scan(
    payload: ScanCreate, session: AsyncSession = Depends(get_session)
) -> ScanOut:
    s = get_settings()
    root_url = str(payload.root_url).rstrip("/")
    domain = canonical_domain(root_url)
    if not domain:
        raise HTTPException(status_code=400, detail="invalid root_url")

    scan = await create_scan(
        session,
        domain=domain,
        root_url=root_url,
        status="pending",
        crawl_depth=payload.crawl_depth,
        page_limit=payload.page_limit,
        use_secondary=payload.use_secondary,
        store_screenshots=payload.store_screenshots,
        strict_mode=payload.strict_mode,
    )
    await session.commit()

    options: Dict[str, Any] = {
        "crawl_depth": payload.crawl_depth,
        "page_limit": payload.page_limit,
        "use_secondary": payload.use_secondary,
        "store_screenshots": payload.store_screenshots,
        "strict_mode": payload.strict_mode,
    }
    schedule(scan.id, options, root_url, domain)
    return _scan_to_out(scan, findings_count=0, pages_count=0)


@router.get("/scans", response_model=List[ScanListItem])
async def list_all_scans(
    domain: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> List[ScanListItem]:
    scans = await list_scans(session, domain=domain, limit=limit)
    # Small n+1 for findings_count is fine here.
    out: List[ScanListItem] = []
    for s in scans:
        count = (await session.execute(
            select(Finding).where(Finding.scan_id == s.id)
        )).scalars().all()
        out.append(
            ScanListItem(
                id=s.id,
                domain=s.domain,
                root_url=s.root_url,
                status=s.status,  # type: ignore[arg-type]
                created_at=s.created_at,
                score=s.score,
                grade=s.grade,
                findings_count=len(count),
            )
        )
    return out


@router.get("/scans/{scan_id}", response_model=ScanDetail)
async def get_scan_detail(
    scan_id: str, session: AsyncSession = Depends(get_session)
) -> ScanDetail:
    scan = await get_scan(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan not found")
    pages = await get_pages(session, scan_id)
    findings = await get_findings(session, scan_id)

    findings_per_page = {p.id: 0 for p in pages}
    for f in findings:
        findings_per_page[f.page_id] = findings_per_page.get(f.page_id, 0) + 1

    page_outs = [
        PageOut(
            id=p.id,
            url=p.url,
            final_url=p.final_url,
            title=p.title,
            http_status=p.http_status,
            status=p.status,
            error=p.error,
            screenshot_url=to_public_url(p.screenshot_path),
            findings_count=findings_per_page.get(p.id, 0),
        )
        for p in pages
    ]
    return ScanDetail(
        **_scan_to_out(scan, findings_count=len(findings), pages_count=len(pages)).model_dump(),
        pages=page_outs,
    )


@router.get("/scans/{scan_id}/findings", response_model=ScanFindings)
async def get_scan_findings(
    scan_id: str, session: AsyncSession = Depends(get_session)
) -> ScanFindings:
    scan = await get_scan(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan not found")
    pages = await get_pages(session, scan_id)
    findings = await get_findings(session, scan_id)
    by_page: Dict[str, List[Finding]] = {}
    for f in findings:
        by_page.setdefault(f.page_id, []).append(f)

    grouped: List[FindingsByPage] = []
    for p in pages:
        page_findings = by_page.get(p.id, [])
        grouped.append(
            FindingsByPage(
                page=PageOut(
                    id=p.id,
                    url=p.url,
                    final_url=p.final_url,
                    title=p.title,
                    http_status=p.http_status,
                    status=p.status,
                    error=p.error,
                    screenshot_url=to_public_url(p.screenshot_path),
                    findings_count=len(page_findings),
                ),
                findings=[_finding_to_out(f, p) for f in page_findings],
            )
        )
    return ScanFindings(scan_id=scan_id, pages=grouped)


@router.get("/scans/{scan_id}/history", response_model=List[ScanListItem])
async def get_scan_history(
    scan_id: str, session: AsyncSession = Depends(get_session)
) -> List[ScanListItem]:
    scan = await get_scan(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan not found")
    prior = await list_scans_for_domain(session, scan.domain, exclude_id=scan_id)
    out: List[ScanListItem] = []
    for s in prior:
        count = (await session.execute(
            select(Finding).where(Finding.scan_id == s.id)
        )).scalars().all()
        out.append(
            ScanListItem(
                id=s.id,
                domain=s.domain,
                root_url=s.root_url,
                status=s.status,  # type: ignore[arg-type]
                created_at=s.created_at,
                score=s.score,
                grade=s.grade,
                findings_count=len(count),
            )
        )
    return out


@router.get("/scans/{scan_id}/compare/{previous_scan_id}", response_model=CompareResult)
async def compare_scans(
    scan_id: str,
    previous_scan_id: str,
    session: AsyncSession = Depends(get_session),
) -> CompareResult:
    scan = await get_scan(session, scan_id)
    prev = await get_scan(session, previous_scan_id)
    if not scan or not prev:
        raise HTTPException(status_code=404, detail="scan not found")
    if scan.domain != prev.domain:
        raise HTTPException(status_code=400, detail="scans belong to different domains")
    current = await get_findings(session, scan_id)
    previous = await get_findings(session, previous_scan_id)

    from ..agents.memory import _diff_summaries  # local import to avoid cycle at startup

    summary = _diff_summaries(current, previous)
    summary["score_delta"] = (
        None if scan.score is None or prev.score is None
        else round(float(scan.score) - float(prev.score), 2)
    )
    await save_comparison(session, scan_id, previous_scan_id, summary)
    await session.commit()
    return CompareResult(
        scan_id=scan_id,
        previous_scan_id=previous_scan_id,
        new_issues=summary["new_issues"],
        resolved_issues=summary["resolved_issues"],
        recurring_issues=summary["recurring_issues"],
        delta=summary["delta"],
        score_delta=summary.get("score_delta"),
    )


@router.get("/scans/{scan_id}/artifacts")
async def get_scan_artifacts(
    scan_id: str, session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    scan = await get_scan(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="scan not found")
    pages = await get_pages(session, scan_id)
    findings = await get_findings(session, scan_id)
    return {
        "scan_id": scan_id,
        "status": scan.status,
        "summary_md": scan.summary_md,
        "stats": scan.stats_json,
        "page_screenshots": [
            {"page_id": p.id, "url": p.url, "screenshot_url": to_public_url(p.screenshot_path)}
            for p in pages
            if p.screenshot_path
        ],
        "annotated_findings": [
            {
                "finding_id": f.id,
                "rule_id": f.rule_id,
                "annotated_url": to_public_url(f.annotated_screenshot_path),
            }
            for f in findings
            if f.annotated_screenshot_path
        ],
    }


# ---------- helpers ----------

def _scan_to_out(scan: Scan, findings_count: int, pages_count: int) -> ScanOut:
    return ScanOut(
        id=scan.id,
        domain=scan.domain,
        root_url=scan.root_url,
        status=scan.status,  # type: ignore[arg-type]
        created_at=scan.created_at,
        updated_at=scan.updated_at,
        score=scan.score,
        grade=scan.grade,
        executive_summary=scan.executive_summary,
        stats=scan.stats_json,
        error=scan.error,
        pages_count=pages_count,
        findings_count=findings_count,
    )


def _finding_to_out(f: Finding, page: Page) -> FindingOut:
    refs = []
    for r in f.wcag_refs_json or []:
        refs.append(
            WcagReference(
                criterion=r.get("criterion", "WCAG"),
                level=r.get("level"),
                url=r.get("url"),
                snippet=r.get("snippet"),
            )
        )
    rem = None
    if f.remediation_json:
        rem = Remediation(
            explanation=f.remediation_json.get("explanation", ""),
            why_it_matters=f.remediation_json.get("why_it_matters", ""),
            how_to_fix=f.remediation_json.get("how_to_fix", ""),
            code_snippet=f.remediation_json.get("code_snippet"),
            implementation_notes=f.remediation_json.get("implementation_notes"),
            grounded=bool(f.remediation_json.get("grounded")),
        )
    return FindingOut(
        id=f.id,
        rule_id=f.rule_id,
        title=f.title,
        severity=f.severity,  # type: ignore[arg-type]
        source=f.source,
        confidence=f.confidence,  # type: ignore[arg-type]
        page_url=page.final_url or page.url,
        selector=f.selector,
        html_snippet=f.html_snippet,
        description=f.description,
        help_text=f.help_text,
        help_url=f.help_url,
        bbox=f.bbox_json,
        annotated_screenshot_url=to_public_url(f.annotated_screenshot_path),
        wcag_refs=refs,
        remediation=rem,
    )
